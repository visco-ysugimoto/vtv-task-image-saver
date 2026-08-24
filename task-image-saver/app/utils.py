"""
ユーティリティ関数を定義するモジュール
"""
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from PIL import Image

from security_limits import (
    MAX_ZIP_TEXT_BYTES,
    open_image_file,
    read_zip_member,
    safe_zip_extract_prefixes,
    safe_zip_extractall,
)


TASK_FILE_EXTENSIONS = (".ziq", ".zit", ".zii", ".zig", ".zia", ".zip")
TASK_FILE_DIALOG_TYPES = [
    ("Task Files", "*.ziq"),
    ("Task Files", "*.zit"),
    ("Task Files", "*.zii"),
    ("Task Files", "*.zig"),
    ("Task Files", "*.zia"),
    ("ZIP Files", "*.zip"),
    ("All Files", "*.*"),
]
TASK_FILE_EXTENSIONS_LABEL = "ziq / zit / zii / zig / zia / zip"
TASK_FOLDER_RE = re.compile(r"(?i)(^|.*/)viscotech/task/(g\d+)/([^/]+)/")


@dataclass
class TaskFolder:
    """タスクファイル内の viscotech/task/gXX/<task> 1件分。"""

    prefix: str
    label: str
    title: str = ""
    comment: str = ""
    updated_at: str = ""
    image_count: int = 0


@dataclass
class TaskZipMetadata:
    """タスク ZIP 内の ver.txt / info.txt から得た表示用メタデータ。"""

    version: Optional[str] = None
    title: Optional[str] = None
    comment: Optional[str] = None
    last_updated: Optional[str] = None


@dataclass
class TaskImageSource:
    """img フォルダ内の参照用 txt 1件と、そこに記載された BMP。"""

    txt_name: str
    comment: str = ""
    bmp_paths: list[str] = field(default_factory=list)


def format_value(value: str) -> str:
    """
    1桁の数字に対して、先頭に0を付ける関数

    Args:
        value: 数値文字列

    Returns:
        2桁にフォーマットされた文字列（変換不可の場合は "00"）
    """
    try:
        return f"{int(value):02d}"
    except (ValueError, TypeError):
        return "00"


def convert_bmp_to_jpeg(folder: str, quality: int = 85,
                        progress_callback: Optional[Callable] = None,
                        cancel_check: Optional[Callable] = None) -> None:
    """
    指定フォルダ内のBMPファイルをJPEGに変換し、元のBMPファイルを削除する関数。

    Args:
        folder: BMPファイルが含まれるフォルダのパス
        quality: JPEG保存時の圧縮率（1〜100）。デフォルトは85。
        progress_callback: 進捗を報告するコールバック (current, total, message) -> None
        cancel_check: キャンセル状態をチェックするコールバック () -> bool
    """
    folder_path = Path(folder)

    if not folder_path.exists():
        print(f"フォルダ '{folder}' が存在しません。変換をスキップします。")
        return

    bmp_files = [
        file_path for file_path in folder_path.iterdir()
        if file_path.is_file() and file_path.suffix.lower() == ".bmp"
    ]
    total_files = len(bmp_files)
    converted_count = 0
    error_count = 0

    for i, bmp_file in enumerate(bmp_files):
        if cancel_check and cancel_check():
            print("圧縮処理がキャンセルされました")
            if progress_callback:
                progress_callback(i, total_files, "キャンセルされました")
            return

        if progress_callback:
            progress_callback(i, total_files, f"圧縮中: {bmp_file.name}")

        try:
            jpg_file = bmp_file.with_suffix(".jpg")

            with open_image_file(bmp_file) as img:
                img = img.convert("RGB")
                img.save(jpg_file, "JPEG", quality=quality)

            bmp_file.unlink()
            print(f"変換完了: {bmp_file.name} -> {jpg_file.name} (品質={quality})")
            converted_count += 1

        except Exception as e:
            print(f"変換エラー ({bmp_file.name}): {e}")
            error_count += 1

    if progress_callback:
        progress_callback(total_files, total_files, "圧縮完了")

    if converted_count > 0:
        print(f"変換完了: {converted_count}個のファイルを変換しました。")
    if error_count > 0:
        print(f"警告: {error_count}個のファイルでエラーが発生しました。")


def is_task_file_path(file_path: str) -> bool:
    return bool(file_path) and file_path.lower().endswith(TASK_FILE_EXTENSIONS)


def list_task_folders(task_file_path: str) -> list[TaskFolder]:
    """タスクファイル内の viscotech/task/gXX/<task> フォルダを列挙する。"""
    with zipfile.ZipFile(task_file_path, "r") as zip_ref:
        normalized_names = [name.replace("\\", "/") for name in zip_ref.namelist()]
    return discover_task_folders(normalized_names)


def list_task_folders_with_metadata(task_file_path: str) -> list[TaskFolder]:
    """タスクフォルダ一覧に info.txt のタイトル・コメントを付与して返す。"""
    with zipfile.ZipFile(task_file_path, "r") as zip_ref:
        raw_names = zip_ref.namelist()
        normalized_names = [name.replace("\\", "/") for name in raw_names]
        norm_to_raw = _normalized_to_raw_map(raw_names, normalized_names)
        folders = discover_task_folders(normalized_names)

        for folder in folders:
            folder.image_count = _count_task_bmp_files(
                normalized_names, folder.prefix)
            info_path = _find_task_info_path(normalized_names, folder.prefix)
            if not info_path:
                continue
            try:
                raw_text = read_zip_member(
                    zip_ref,
                    norm_to_raw.get(info_path, info_path),
                    max_bytes=MAX_ZIP_TEXT_BYTES,
                ).decode("utf-8-sig", errors="ignore")
                title, comment, updated_at = parse_task_info_txt(raw_text)
                folder.title = title or ""
                folder.comment = comment or ""
                folder.updated_at = updated_at or ""
            except Exception as ex:
                print(f"info.txt の読込に失敗しました: {info_path} - {ex}")

    return folders


def discover_task_folders(normalized_names: list[str]) -> list[TaskFolder]:
    folders: dict[str, TaskFolder] = {}
    for name in normalized_names:
        match = TASK_FOLDER_RE.search(name)
        if not match:
            continue
        prefix = name[: match.end()].rstrip("/")
        group = match.group(2)
        task = match.group(3)
        folders.setdefault(prefix, TaskFolder(prefix=prefix, label=f"{group}/{task}"))
    return sorted(folders.values(), key=lambda folder: _task_folder_sort_key(folder.label))


FILESYSTEM_GROUP_DIR_RE = re.compile(r"^g\d+$", re.IGNORECASE)


def find_task_info_path_on_disk(task_dir: str) -> Optional[str]:
    """タスクフォルダ配下の info.txt を探す（大文字小文字を区別しない）。"""
    if not os.path.isdir(task_dir):
        return None

    direct = os.path.join(task_dir, "info.txt")
    if os.path.isfile(direct):
        return direct

    try:
        for name in os.listdir(task_dir):
            if name.lower() != "info.txt":
                continue
            path = os.path.join(task_dir, name)
            if os.path.isfile(path):
                return path
    except OSError:
        return None
    return None


def _decode_task_info_bytes(raw: bytes) -> list[str]:
    """info.txt バイト列を複数エンコーディングでデコードして候補文字列を返す。"""
    candidates: list[str] = []
    seen: set[str] = set()
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text not in seen:
            seen.add(text)
            candidates.append(text)
    if not candidates:
        candidates.append(raw.decode("utf-8", errors="ignore"))
    return candidates


def _format_info_file_mtime(info_path: str) -> str:
    try:
        mtime = os.path.getmtime(info_path)
        return datetime.fromtimestamp(mtime).strftime("%Y/%m/%d %H:%M")
    except OSError:
        return ""


TASK_LIST_DAT_FILENAME = "taskList.dat"
TASK_LIST_BLOCK_SIZE = 50
_PLACEHOLDER_TASK_TITLES = frozenset({"未登録", ""})


def _viscotech_root_from_task_dir(task_dir: str) -> str:
    """{viscotech}/task/gXX/YY から {viscotech} を返す。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(task_dir)))


def _folder_group_task_ids(task_dir: str) -> tuple[int, int, str]:
    """タスクフォルダパスから (group_num, task_num, task_folder_name) を返す。"""
    task_name = os.path.basename(task_dir)
    group_name = os.path.basename(os.path.dirname(task_dir))
    group_num = int(re.sub(r"^g", "", group_name, flags=re.IGNORECASE))
    task_num = int(task_name)
    return group_num, task_num, task_name


def _task_list_data_line_index(group_num: int, task_num: int) -> int:
    """taskList.dat 内のデータ行インデックス(0-based)を返す。"""
    return 1 + (group_num - 1) * TASK_LIST_BLOCK_SIZE + (task_num - 1)


def _is_usable_task_title(title: Optional[str]) -> bool:
    if not title:
        return False
    return title.strip() not in _PLACEHOLDER_TASK_TITLES


def _is_usable_updated_at(updated_at: Optional[str]) -> bool:
    if not updated_at:
        return False
    normalized = updated_at.strip()
    if not normalized:
        return False
    if normalized.startswith("0000/"):
        return False
    if normalized.startswith("0000-"):
        return False
    return True


def _default_task_title(task_folder_name: str) -> str:
    """VTV 既定のタスク名（例: フォルダ 01 → タスク01）。"""
    return f"タスク{format_value(task_folder_name)}"


def _latest_image_mtime(img_dir: str) -> str:
    """img フォルダ内 BMP の最新更新日時を表示用文字列で返す。"""
    if not os.path.isdir(img_dir):
        return ""
    latest_mtime = 0.0
    try:
        for name in os.listdir(img_dir):
            if not name.lower().endswith(".bmp"):
                continue
            path = os.path.join(img_dir, name)
            if not os.path.isfile(path):
                continue
            latest_mtime = max(latest_mtime, os.path.getmtime(path))
    except OSError:
        return ""
    if latest_mtime <= 0:
        return ""
    return datetime.fromtimestamp(latest_mtime).strftime("%Y/%m/%d %H:%M")


def load_task_list_dat_index(
    viscotech_root: str,
) -> dict[tuple[int, int], tuple[str, str, str]]:
    """taskList.dat を (group_num, task_num) キーの辞書に読み込む。

    taskList.dat はヘッダー1行の後、グループごとに50行(タスク01〜50)の
    固定ブロック構造。g02/01 は 2番目のブロック先頭行に対応する。
    """
    path = os.path.join(viscotech_root, TASK_LIST_DAT_FILENAME)
    if not os.path.isfile(path):
        return {}

    try:
        with open(path, "rb") as dat_file:
            raw = dat_file.read(MAX_ZIP_TEXT_BYTES)
    except OSError as ex:
        print(f"taskList.dat の読込に失敗しました: {path} - {ex}")
        return {}

    index: dict[tuple[int, int], tuple[str, str, str]] = {}
    for raw_text in _decode_task_info_bytes(raw):
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        header_line = lines[0]
        data_line_count = len(lines) - 1
        max_group = (
            (data_line_count + TASK_LIST_BLOCK_SIZE - 1) // TASK_LIST_BLOCK_SIZE
        )
        for group_num in range(1, max_group + 1):
            for task_num in range(1, TASK_LIST_BLOCK_SIZE + 1):
                line_idx = _task_list_data_line_index(group_num, task_num)
                if line_idx >= len(lines):
                    break
                data_line = lines[line_idx]
                if not data_line:
                    continue
                title, comment, updated_at = parse_task_info_txt(
                    f"{header_line}\n{data_line}",
                )
                index[(group_num, task_num)] = (
                    title or "",
                    comment or "",
                    updated_at or "",
                )
        if index:
            return index
    return index


def resolve_task_folder_metadata(
    task_dir: str,
    task_list_index: Optional[dict[tuple[int, int], tuple[str, str, str]]] = None,
) -> tuple[str, str, str]:
    """info.txt / taskList.dat / 画像更新日時から表示用メタデータを解決する。"""
    title, comment, updated_at = read_task_folder_info(task_dir)
    group_num, task_num, task_name = _folder_group_task_ids(task_dir)

    if task_list_index is None:
        viscotech_root = _viscotech_root_from_task_dir(task_dir)
        task_list_index = load_task_list_dat_index(viscotech_root)

    list_entry = task_list_index.get((group_num, task_num))
    if list_entry:
        list_title, list_comment, list_updated = list_entry
        if not _is_usable_task_title(title) and _is_usable_task_title(list_title):
            title = list_title
        if not comment and list_comment:
            comment = list_comment
        if not _is_usable_updated_at(updated_at) and _is_usable_updated_at(list_updated):
            updated_at = list_updated

    if not _is_usable_task_title(title):
        title = _default_task_title(task_name)

    if not _is_usable_updated_at(updated_at):
        img_dir = os.path.join(task_dir, "img")
        updated_at = _latest_image_mtime(img_dir)
        if not updated_at:
            try:
                updated_at = _format_info_file_mtime(task_dir)
            except OSError:
                updated_at = ""

    return title, comment, updated_at


def read_task_folder_info(
    task_dir: str,
) -> tuple[str, str, str]:
    """{task_dir}/info.txt から (title, comment, updated_at) を返す。"""
    info_path = find_task_info_path_on_disk(task_dir)
    if not info_path:
        return "", "", ""
    try:
        with open(info_path, "rb") as info_file:
            raw = info_file.read(MAX_ZIP_TEXT_BYTES)
    except OSError as ex:
        print(f"info.txt の読込に失敗しました: {info_path} - {ex}")
        return "", "", ""

    best = ("", "", "")
    for raw_text in _decode_task_info_bytes(raw):
        title, comment, updated_at = parse_task_info_txt(raw_text)
        parsed = (title or "", comment or "", updated_at or "")
        if any(parsed):
            return parsed
        best = parsed

    fallback_updated = _format_info_file_mtime(info_path)
    return best[0], best[1], best[2] or fallback_updated


def count_task_bmp_files(img_dir: str) -> int:
    """img フォルダ内の BMP ファイル数を返す。"""
    if not os.path.isdir(img_dir):
        return 0
    return sum(
        1
        for name in os.listdir(img_dir)
        if name.lower().endswith(".bmp")
        and os.path.isfile(os.path.join(img_dir, name))
    )


def _list_folder_bmp_paths(img_folder: str) -> list[str]:
    """img フォルダ直下の BMP 絶対パスをソートして返す。"""
    return sorted(
        os.path.join(img_folder, name)
        for name in os.listdir(img_folder)
        if name.lower().endswith(".bmp")
        and os.path.isfile(os.path.join(img_folder, name))
    )


def _parse_txt_image_references(txt_bytes: bytes) -> tuple[list[str], str]:
    """参照用 txt から FILE= ファイル名と Comment= を取り出す。"""
    referenced_names: list[str] = []
    comment = ""
    for raw_line in txt_bytes.splitlines(keepends=True):
        line = raw_line.decode("utf-8", errors="ignore")
        if not comment and "Comment=" in line:
            comment = line.split("Comment=", 1)[1].strip()
        if "FILE=" in line:
            bmp_name = line.split("FILE=", 1)[1].strip()
            if bmp_name:
                referenced_names.append(bmp_name)
    return referenced_names, comment


def _resolve_referenced_bmp_paths(
    referenced_names: list[str],
    bmp_lookup: dict[str, str],
    fallback: list[str],
) -> list[str]:
    """FILE= 名を実在 BMP パスへ解決する。1件も無い場合は fallback。"""
    resolved: list[str] = []
    for bmp_name in referenced_names:
        full_path = bmp_lookup.get(bmp_name.lower())
        if full_path:
            resolved.append(full_path)
    return resolved if resolved else fallback


def select_task_image_source(
    sources: list[TaskImageSource],
    txt_name: Optional[str] = None,
) -> Optional[TaskImageSource]:
    """txt 名で参照ソースを選ぶ。未指定・不一致なら先頭を返す。"""
    if not sources:
        return None
    if txt_name:
        wanted = txt_name.lower()
        for source in sources:
            if source.txt_name.lower() == wanted:
                return source
    return sources[0]


def list_task_image_sources_from_folder(img_folder: str) -> list[TaskImageSource]:
    """img フォルダ内の参照用 txt ごとに FILE= 順の BMP を返す。"""
    if not os.path.isdir(img_folder):
        return []

    bmp_files = _list_folder_bmp_paths(img_folder)
    txt_files = sorted(
        os.path.join(img_folder, name)
        for name in os.listdir(img_folder)
        if name.lower().endswith(".txt")
        and os.path.isfile(os.path.join(img_folder, name))
    )
    if not txt_files:
        return []

    bmp_lookup = {
        os.path.basename(path).lower(): path
        for path in bmp_files
    }
    sources: list[TaskImageSource] = []
    for txt_path in txt_files:
        try:
            with open(txt_path, "rb") as txt_file:
                txt_bytes = txt_file.read(MAX_ZIP_TEXT_BYTES)
        except OSError:
            continue
        referenced_names, comment = _parse_txt_image_references(txt_bytes)
        sources.append(
            TaskImageSource(
                txt_name=os.path.basename(txt_path),
                comment=comment,
                bmp_paths=_resolve_referenced_bmp_paths(
                    referenced_names, bmp_lookup, [],
                ),
            )
        )
    return sources


def extract_ordered_bmp_paths_from_folder(
    img_folder: str,
    txt_name: Optional[str] = None,
) -> list[str]:
    """img フォルダ内の FILE= 順 BMP 絶対パス一覧を返す。"""
    if not os.path.isdir(img_folder):
        return []

    bmp_files = _list_folder_bmp_paths(img_folder)
    sources = list_task_image_sources_from_folder(img_folder)
    if not sources:
        return bmp_files
    selected = select_task_image_source(sources, txt_name)
    if selected is None:
        return bmp_files
    return selected.bmp_paths or bmp_files


def list_filesystem_task_folders(task_root: str) -> list[TaskFolder]:
    """{task_root}/gXX/YY/ を走査し TaskFolder 一覧を返す。"""
    folders: list[TaskFolder] = []
    if not os.path.isdir(task_root):
        return folders

    viscotech_root = os.path.dirname(task_root)
    task_list_index = load_task_list_dat_index(viscotech_root)

    for group_name in sorted(os.listdir(task_root)):
        if not FILESYSTEM_GROUP_DIR_RE.match(group_name):
            continue
        group_path = os.path.join(task_root, group_name)
        if not os.path.isdir(group_path):
            continue

        for task_name in sorted(os.listdir(group_path)):
            task_path = os.path.join(group_path, task_name)
            if not os.path.isdir(task_path):
                continue

            img_path = os.path.join(task_path, "img")
            title, comment, updated_at = resolve_task_folder_metadata(
                task_path,
                task_list_index,
            )
            folders.append(
                TaskFolder(
                    prefix=os.path.abspath(task_path),
                    label=f"{group_name}/{task_name}",
                    title=title,
                    comment=comment,
                    updated_at=updated_at,
                    image_count=count_task_bmp_files(img_path),
                )
            )

    return sorted(folders, key=lambda folder: _task_folder_sort_key(folder.label))


def list_task_image_sources_from_zip(
    task_file_path: str,
    task_prefix: Optional[str] = None,
) -> list[TaskImageSource]:
    """タスクファイル内の参照用 txt ごとに FILE= 順の BMP を返す。"""
    with zipfile.ZipFile(task_file_path, "r") as zip_ref:
        raw_names = zip_ref.namelist()
        normalized_names = [name.replace("\\", "/") for name in raw_names]
        norm_to_raw = _normalized_to_raw_map(raw_names, normalized_names)

        img_prefix = _find_img_prefix(normalized_names, task_prefix)
        if not img_prefix:
            return []

        bmp_lookup = {
            os.path.basename(name).lower(): norm_to_raw.get(name, name)
            for name in normalized_names
            if name.startswith(img_prefix) and name.lower().endswith(".bmp")
        }
        txt_files = sorted(
            name
            for name in normalized_names
            if name.startswith(img_prefix) and name.lower().endswith(".txt")
        )
        sources: list[TaskImageSource] = []
        for txt_name in txt_files:
            txt_bytes = read_zip_member(
                zip_ref,
                norm_to_raw.get(txt_name, txt_name),
                max_bytes=MAX_ZIP_TEXT_BYTES,
            )
            referenced_names, comment = _parse_txt_image_references(txt_bytes)
            sources.append(
                TaskImageSource(
                    txt_name=os.path.basename(txt_name),
                    comment=comment,
                    bmp_paths=_resolve_referenced_bmp_paths(
                        referenced_names, bmp_lookup, [],
                    ),
                )
            )
        return sources


def extract_ordered_bmp_paths_from_zip(
    task_file_path: str,
    task_prefix: Optional[str] = None,
    txt_name: Optional[str] = None,
) -> list[str]:
    """タスクファイル内の選択タスクから FILE= 順の BMP パスを返す。"""
    sources = list_task_image_sources_from_zip(task_file_path, task_prefix)
    selected = select_task_image_source(sources, txt_name)
    if selected and selected.bmp_paths:
        return selected.bmp_paths

    with zipfile.ZipFile(task_file_path, "r") as zip_ref:
        raw_names = zip_ref.namelist()
        normalized_names = [name.replace("\\", "/") for name in raw_names]
        norm_to_raw = _normalized_to_raw_map(raw_names, normalized_names)
        img_prefix = _find_img_prefix(normalized_names, task_prefix)
        if not img_prefix:
            return []
        return sorted(
            norm_to_raw.get(name, name)
            for name in normalized_names
            if name.startswith(img_prefix) and name.lower().endswith(".bmp")
        )


def _find_img_prefix(
    normalized_names: list[str],
    task_prefix: Optional[str] = None,
) -> Optional[str]:
    if task_prefix:
        expected = task_prefix.rstrip("/") + "/img/"
        for name in normalized_names:
            if name.startswith(expected):
                return expected
        return None

    for name in normalized_names:
        if "/img/" in name:
            index = name.index("/img/")
            return name[: index + len("/img/")]
    return None


def _find_task_info_path(
    normalized_names: list[str],
    task_prefix: str,
) -> Optional[str]:
    """viscotech/task/gXX/YY/info.txt。直接パスに加え img 隣接も探す。"""
    normalized_prefix = task_prefix.rstrip("/")
    expected = f"{normalized_prefix}/info.txt"
    for name in normalized_names:
        if name.lower() == expected.lower():
            return name
    prefix = normalized_prefix + "/"
    for name in normalized_names:
        if name.startswith(prefix) and os.path.basename(name).lower() == "info.txt":
            return name

    img_prefix = _find_img_prefix(normalized_names, task_prefix)
    if img_prefix and img_prefix.endswith("img/"):
        candidate = img_prefix[: -len("img/")] + "info.txt"
        for name in normalized_names:
            if name.lower() == candidate.lower():
                return name
    return None


def _count_task_bmp_files(
    normalized_names: list[str],
    task_prefix: str,
) -> int:
    img_prefix = _find_img_prefix(normalized_names, task_prefix)
    if not img_prefix:
        return 0
    return sum(
        1
        for name in normalized_names
        if name.startswith(img_prefix) and name.lower().endswith(".bmp")
    )


def _normalized_to_raw_map(
    raw_names: list[str],
    normalized_names: list[str],
) -> dict[str, str]:
    norm_to_raw: dict[str, str] = {}
    for raw, norm in zip(raw_names, normalized_names):
        norm_to_raw.setdefault(norm, raw)
    return norm_to_raw


def _task_folder_sort_key(label: str) -> tuple[int, str, int, str]:
    group, _, task = label.partition("/")
    return _first_int(group), group.lower(), _first_int(task), task.lower()


def _first_int(value: str) -> int:
    match = re.search(r"\d+", value)
    if not match:
        return 10**9
    return int(match.group(0))


def parse_task_info_txt(raw_text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """info.txt 全文から (タイトル, コメント, 更新日表示文字列) を返す。"""
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        return None, None, None
    header_line = lines[0]
    data_line = lines[1] if len(lines) >= 2 else lines[0]
    length_row_hint = (
        _header_suggests_length_prefixed(header_line)
        or _data_row_looks_length_prefixed(data_line)
    )
    if length_row_hint:
        parsed = _parse_v2_length_prefixed_line(data_line)
        if parsed is not None:
            return parsed
    return _parse_v1_split_parts(data_line.split(","), length_row_hint)


def _header_suggests_length_prefixed(header_line: str) -> bool:
    hparts = header_line.split(",")
    if len(hparts) < 2:
        return False
    try:
        return int(hparts[1].strip()) >= 2
    except ValueError:
        return False


def _data_row_looks_length_prefixed(data_line: str) -> bool:
    parts = data_line.split(",")
    if len(parts) < 5 or not _is_plain_int_token(parts[3]):
        return False
    if parts[0] == "102" and parts[1] == "2" and parts[2] == "2":
        return True
    return _parse_v2_length_prefixed_line(data_line) is not None


def _parse_v2_length_prefixed_line(
    data_line: str,
) -> Optional[tuple[Optional[str], Optional[str], Optional[str]]]:
    pos = 0
    for _ in range(3):
        idx = data_line.find(",", pos)
        if idx < 0:
            return None
        pos = idx + 1
    idx = data_line.find(",", pos)
    if idx < 0:
        return None
    try:
        title_len = int(data_line[pos:idx].strip())
    except ValueError:
        return None
    if title_len < 0:
        return None

    title_start = idx + 1
    if title_start + title_len > len(data_line):
        return None
    title = data_line[title_start:title_start + title_len]
    parts_csv = data_line.split(",")
    if (
        len(parts_csv) > 5
        and _is_plain_int_token(parts_csv[3])
        and title_len > len(parts_csv[4])
        and title == parts_csv[4] + "," + parts_csv[5]
        and _is_plain_int_token(parts_csv[5])
    ):
        title = parts_csv[4]

    pos = title_start + len(title)
    if pos >= len(data_line) or data_line[pos] != ",":
        return None
    pos += 1

    for n_skip in (1, 0, 2):
        got = _parse_v2_after_title(data_line, pos, n_skip)
        if got is not None:
            comment, updated_at = got
            return title or None, comment, updated_at
    return None


def _parse_v2_after_title(
    data_line: str,
    pos: int,
    n_skip: int,
) -> Optional[tuple[Optional[str], Optional[str]]]:
    p = pos
    for _ in range(n_skip):
        idx = data_line.find(",", p)
        if idx < 0 or not _is_plain_int_token(data_line[p:idx]):
            return None
        p = idx + 1
    idx = data_line.find(",", p)
    if idx < 0:
        return None
    try:
        comment_len = int(data_line[p:idx].strip())
    except ValueError:
        return None
    if comment_len < 0:
        return None
    p = idx + 1
    if p + comment_len > len(data_line):
        return None
    comment = data_line[p:p + comment_len]
    p += comment_len
    tail = data_line[p + 1:] if data_line[p:].startswith(",") else data_line[p:]
    tail_parts = tail.split(",") if tail else []
    anchor = _find_datetime_anchor(tail_parts)
    if anchor is None:
        return None
    return comment or None, _format_datetime_at(tail_parts, anchor)


def _parse_v1_split_parts(
    parts: list[str],
    v2_header_hint: bool = False,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    anchor = _find_datetime_anchor(parts)
    if anchor is not None:
        mid = parts[4:anchor - 5]
        title, comment = _split_title_comment_mid(mid, v2_header_hint)
        return title, comment, _format_datetime_at(parts, anchor)

    title = _csv_field(parts, 4)
    comment = _csv_field(parts, 6)
    return title, comment, _format_datetime_at(parts, 11)


def _split_title_comment_mid(
    mid: list[str],
    v2_header_hint: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    if not mid:
        return None, None
    if len(mid) == 1:
        value = mid[0].strip()
        return (value if value else None), None
    if len(mid) == 2:
        title, comment = mid[0].strip(), mid[1].strip()
        return (title if title else None), (comment if comment else None)

    title = mid[0].strip()
    rest = mid[1:]
    if v2_header_hint and len(rest) >= 2 and _is_plain_int_token(rest[0]):
        try:
            comment_len = int(rest[0].strip())
        except ValueError:
            comment_len = -1
        body = ",".join(rest[1:]).strip()
        if comment_len >= 0 and len(body) == comment_len:
            return (title if title else None), (body if body else None)

    comment = ",".join(rest).strip()
    return (title if title else None), (comment if comment else None)


def _csv_field(parts: list[str], index: int) -> Optional[str]:
    if index >= len(parts):
        return None
    value = parts[index].strip()
    return value if value else None


def _find_datetime_anchor(parts: list[str]) -> Optional[int]:
    for index in range(len(parts) - 6, 4, -1):
        if _five_int_tokens(parts[index - 5:index]) and _valid_datetime_six(parts, index):
            return index
    return None


def _five_int_tokens(slice5: list[str]) -> bool:
    return len(slice5) == 5 and all(_is_plain_int_token(token) for token in slice5)


def _is_plain_int_token(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    if value.startswith("-"):
        value = value[1:]
    return bool(value) and value.isdigit()


def _valid_datetime_six(parts: list[str], index: int) -> bool:
    if index + 6 > len(parts):
        return False
    try:
        year = int(parts[index])
        month = int(parts[index + 1])
        day = int(parts[index + 2])
        hour = int(parts[index + 4])
        minute = int(parts[index + 5])
    except (TypeError, ValueError):
        return False
    return (
        1990 <= year <= 2100
        and 1 <= month <= 12
        and 1 <= day <= 31
        and 0 <= hour <= 23
        and 0 <= minute <= 59
    )


def _format_datetime_at(parts: list[str], index: int) -> Optional[str]:
    try:
        year = int(parts[index])
        month = int(parts[index + 1])
        day = int(parts[index + 2])
        hour = int(parts[index + 4])
        minute = int(parts[index + 5])
    except (IndexError, TypeError, ValueError):
        return None
    return f"{year:04d}/{month:02d}/{day:02d} {hour:02d}:{minute:02d}"


def pick_sample_paths(
    all_paths: list[str],
    max_images: Optional[int],
) -> list[str]:
    """表示上限。None なら全件。超える場合は先頭から昇順で max_images 件。"""
    if not all_paths:
        return []
    if max_images is None:
        return list(all_paths)
    return list(all_paths[:max_images])


def parse_task_version_text(raw_text: str) -> Optional[str]:
    """ver.txt: 1〜3行が版、5行目がビルド番号。"""
    lines = [line.strip() for line in raw_text.splitlines()]
    if len(lines) < 5:
        return None
    major, minor, patch, build = lines[0], lines[1], lines[2], lines[4]
    if not all((major, minor, patch, build)):
        return None
    return f"{major}.{minor}.{patch}B{build}"


def _find_ver_txt_path(normalized_names: list[str]) -> Optional[str]:
    for name in normalized_names:
        lower = name.lower()
        if lower == "viscotech/ver.txt" or lower.endswith("/viscotech/ver.txt"):
            return name
    return None


def _format_zip_date_time(zi: zipfile.ZipInfo) -> str:
    y, m, d, hh, mm, ss = zi.date_time
    return f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}"


def extract_task_zip_metadata(
    task_file_path: str,
    task_prefix: Optional[str] = None,
) -> TaskZipMetadata:
    """ver.txt と info.txt から TaskZipMetadata を組み立てる。"""
    with zipfile.ZipFile(task_file_path, "r") as zip_ref:
        raw_names = zip_ref.namelist()
        normalized_names = [name.replace("\\", "/") for name in raw_names]
        norm_to_raw = _normalized_to_raw_map(raw_names, normalized_names)

        version: Optional[str] = None
        last_from_zip: Optional[str] = None
        ver_path = _find_ver_txt_path(normalized_names)
        if ver_path:
            raw_ver = read_zip_member(
                zip_ref,
                norm_to_raw.get(ver_path, ver_path),
                max_bytes=MAX_ZIP_TEXT_BYTES,
            ).decode("utf-8", errors="ignore")
            version = parse_task_version_text(raw_ver)
            try:
                last_from_zip = _format_zip_date_time(
                    zip_ref.getinfo(norm_to_raw.get(ver_path, ver_path))
                )
            except KeyError:
                last_from_zip = None

        title: Optional[str] = None
        comment: Optional[str] = None
        last_from_info: Optional[str] = None
        if task_prefix:
            info_path = _find_task_info_path(normalized_names, task_prefix)
            if info_path:
                raw_info = read_zip_member(
                    zip_ref,
                    norm_to_raw.get(info_path, info_path),
                    max_bytes=MAX_ZIP_TEXT_BYTES,
                ).decode("utf-8-sig", errors="ignore")
                title, comment, last_from_info = parse_task_info_txt(raw_info)

        last_updated = last_from_info or last_from_zip
        return TaskZipMetadata(
            version=version,
            title=title,
            comment=comment,
            last_updated=last_updated,
        )


def extract_task_file(
    task_file_path: str,
    output_folder: str,
    task_prefix: Optional[str] = None,
    task_prefixes: Optional[list[str]] = None,
) -> Optional[str]:
    """
    タスクファイルを解凍し、選択タスクの img フォルダのパスを返す。

    Args:
        task_file_path: タスクファイルのパス
        output_folder: 解凍先フォルダ
        task_prefix: viscotech/task/gXX/<task>。None の場合は最初の img を返す。
        task_prefixes: 展開するタスク prefix の一覧。指定時は該当メンバーのみ展開。

    Returns:
        imgフォルダのパス（見つからない場合はNone）
    """
    try:
        output_path = Path(output_folder)

        with zipfile.ZipFile(task_file_path, "r") as zip_ref:
            if task_prefixes:
                safe_zip_extract_prefixes(
                    zip_ref, output_folder, task_prefixes,
                )
            elif task_prefix:
                safe_zip_extract_prefixes(
                    zip_ref, output_folder, [task_prefix],
                )
            else:
                safe_zip_extractall(zip_ref, output_folder)

        viscotech_folder_path = output_path / "viscotech"
        if task_prefix:
            selected_img_path = output_path / task_prefix / "img"
            if selected_img_path.exists():
                return str(selected_img_path)

        for walk_root, dirs, files in os.walk(viscotech_folder_path):
            if "img" in dirs:
                img_folder_path = Path(walk_root) / "img"
                return str(img_folder_path)

        return None

    except Exception as e:
        print(f"タスクファイルの解凍エラー: {e}")
        raise


def find_img_folder(base_path: str, group_num: str, task_num: str) -> Optional[str]:
    """
    VTV-9000のimgフォルダのパスを構築

    Args:
        base_path: ベースパス（Option 1の場合はNone、Option 3の場合は共有VTVフォルダパス）
        group_num: グループ番号（2桁フォーマット済み）
        task_num: タスク番号（2桁フォーマット済み）

    Returns:
        imgフォルダのパス
    """
    if base_path:
        img_path = Path(base_path) / "task" / f"g{group_num}" / task_num / "img"
    else:
        from config import Constants
        img_path = Path(Constants.DEFAULT_VISCO_TECH_PATH) / f"g{group_num}" / task_num / "img"

    img_path_str = str(img_path)

    if Path(img_path_str).exists():
        return img_path_str
    return None
