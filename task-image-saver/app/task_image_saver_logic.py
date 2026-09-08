"""
タスク画像保存アプリのビジネスロジック（Flet 非依存）。
"""
from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import save_task_images_CamNum_selection
from PIL import Image
from security_limits import (
    ImageSizeError,
    MAX_ZIP_TEXT_BYTES,
    open_image_from_bytes,
    open_image_file,
    read_zip_member,
)
from utils import (
    TaskFolder,
    TaskImageSource,
    TaskZipMetadata,
    convert_bmp_to_jpeg,
    extract_ordered_bmp_paths_from_folder,
    extract_ordered_bmp_paths_from_zip,
    extract_task_file,
    extract_task_zip_metadata,
    list_task_folders_with_metadata,
    list_task_image_sources_from_folder,
    list_task_image_sources_from_zip,
    parse_task_version_text,
    pick_sample_paths,
    resolve_task_folder_metadata,
    select_task_image_source,
    _find_img_prefix,
    _normalized_to_raw_map,
)

ALLOWED_PLACEHOLDERS = {"comment", "tool", "original", "cam", "div", "index", "file"}
PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z0-9_]+)(?::[^{}]+)?\}")


@dataclass
class TaskPreviewLoadResult:
    """タスクファイルの画像プレビュー読み込み結果。"""

    total_bmp_count: int
    thumbnail_bytes: list[bytes]
    thumbnail_paths: list[str]
    all_bmp_paths: list[str]
    metadata: Optional[TaskZipMetadata] = None
    image_sources: list[TaskImageSource] = field(default_factory=list)
    selected_txt_name: str = ""


@dataclass
class ViewerImageAsset:
    """拡大プレビュー用の原寸 BMP 一時ファイル情報。"""

    temp_path: str
    width: int
    height: int


@dataclass
class TemplatePreviewSamples:
    """ファイル名テンプレートプレビュー用のサンプル値"""

    comment: str = "ng"
    tool_capture: str = "画像取込01"
    tool_other: str = "ToolA"
    original: str = "260120115606036_1_1"
    cam: int = 1
    div: int = 2
    index: int = 3
    file: str = "260120115606036"


def extract_unknown_placeholders(template: str) -> list[str]:
    if not template:
        return []
    names = {m.group(1) for m in PLACEHOLDER_PATTERN.finditer(str(template))}
    return sorted(n for n in names if n not in ALLOWED_PLACEHOLDERS)


def parse_int_value(raw: str, default_value: int) -> tuple[int, Optional[str]]:
    """数値文字列をパースする。エラー時は (default, error_message) を返す。"""
    text = (raw or "").strip()
    if text == "":
        return default_value, None
    try:
        return int(text), None
    except ValueError:
        return default_value, "数値を入力してください"


def build_template_preview(
    template: str,
    condition: int,
    samples: TemplatePreviewSamples,
) -> str:
    """テンプレートのプレビュー文字列を生成（condition: 1/2/3）"""
    tool_value = (
        samples.tool_capture if condition == 1 else samples.tool_other
    )
    comment_value = samples.comment if condition in (1, 2) else ""

    try:
        return save_task_images_CamNum_selection.apply_filename_template(
            template=template or "",
            comment=comment_value,
            tool_comment=tool_value,
            original_name=samples.original,
            cam=samples.cam,
            div=samples.div,
            index=samples.index,
            file_source=samples.file,
        )
    except Exception:
        return ""


def task_folder_group(folder: TaskFolder) -> str:
    group, _, _task = folder.label.partition("/")
    return group


def task_folder_task(folder: TaskFolder) -> str:
    _group, _sep, task = folder.label.partition("/")
    return task


def option2_group_labels(task_folders: list[TaskFolder]) -> list[str]:
    labels = []
    for folder in task_folders:
        group = task_folder_group(folder)
        if group and group not in labels:
            labels.append(group)
    return labels


def option2_task_labels_for_group(
    task_folders: list[TaskFolder],
    group: str,
) -> list[str]:
    return [
        task_folder_task(folder)
        for folder in task_folders
        if task_folder_group(folder) == group
    ]


def find_task_folder_by_prefix(
    task_folders: list[TaskFolder],
    prefix: Optional[str],
) -> Optional[TaskFolder]:
    for folder in task_folders:
        if folder.prefix == prefix:
            return folder
    return None


def filter_save_task_folders(
    task_folders: list[TaskFolder],
    save_mode: str,
    selected_prefixes: set[str],
) -> list[TaskFolder]:
    if not task_folders:
        return []
    if save_mode != "selected":
        return list(task_folders)
    return [
        folder for folder in task_folders
        if folder.prefix in selected_prefixes
    ]


def task_output_folder(base_output_folder: str, folder: TaskFolder) -> str:
    group = task_folder_group(folder)
    task = task_folder_task(folder)
    return os.path.join(base_output_folder, group, task)


def build_option1_img_path(group_num: str, task_num: str) -> str:
    return f"C:\\viscotech\\task\\g{group_num}\\{task_num}\\img"


def build_option3_img_path(
    viscotech_folder: str,
    group_num: str,
    task_num: str,
) -> str:
    return os.path.join(
        viscotech_folder, f"task\\g{group_num}\\{task_num}\\img",
    )


def snapshot_output_files(output_folder: str) -> set[str]:
    """出力先配下のファイルを相対パスで取得する。"""
    existing_files: set[str] = set()
    if not os.path.exists(output_folder):
        return existing_files
    for walk_root, _dirs, files in os.walk(output_folder):
        for file_name in files:
            full_path = os.path.join(walk_root, file_name)
            existing_files.add(os.path.relpath(full_path, output_folder))
    return existing_files


def cleanup_extracted_task_folders(
    cleanup_paths: list[str],
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> None:
    """タスクファイル展開時に作成した作業フォルダを削除する。"""
    for cleanup_path in cleanup_paths:
        if not cleanup_path or not os.path.isdir(cleanup_path):
            continue
        try:
            if on_progress:
                on_progress(0, 1, "作業フォルダを削除中...")
            shutil.rmtree(cleanup_path)
            if on_progress:
                on_progress(1, 1, "作業フォルダ削除完了")
            print(f"展開フォルダを削除しました: {cleanup_path}")
        except Exception as ex:
            print(f"展開フォルダの削除に失敗しました: {cleanup_path} - {ex}")


def _resolve_preview_source_bmps(
    sources: list[TaskImageSource],
    txt_name: Optional[str],
    fallback_bmps: Callable[[], list[str]],
) -> tuple[list[str], str]:
    """選択した参照 txt の BMP 一覧を返す。txt が無い場合は fallback。"""
    selected = select_task_image_source(sources, txt_name)
    if selected is None:
        return fallback_bmps(), ""
    if selected.bmp_paths:
        return selected.bmp_paths, selected.txt_name
    if len(sources) <= 1:
        return fallback_bmps(), selected.txt_name
    return [], selected.txt_name


def load_task_file_preview(
    zip_path: str,
    task_prefix: Optional[str] = None,
    max_images: Optional[int] = 12,
    thumb_size: tuple[int, int] = (160, 160),
    txt_name: Optional[str] = None,
) -> TaskPreviewLoadResult:
    """タスクファイルからプレビュー用サムネイルと全 BMP 一覧を取得する。"""
    empty = TaskPreviewLoadResult(0, [], [], [], None)
    try:
        sources = list_task_image_sources_from_zip(zip_path, task_prefix)
        all_bmps, selected_txt_name = _resolve_preview_source_bmps(
            sources,
            txt_name,
            lambda: extract_ordered_bmp_paths_from_zip(zip_path, task_prefix),
        )
        metadata = extract_task_zip_metadata(zip_path, task_prefix)
        selected = pick_sample_paths(all_bmps, max_images)
        if not selected:
            return TaskPreviewLoadResult(
                len(all_bmps), [], [], all_bmps, metadata,
                sources, selected_txt_name,
            )

        def _process_one_bmp(args):
            idx, full_path = args
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    raw = read_zip_member(zf, full_path)
                    img = open_image_from_bytes(raw)
                    img.thumbnail(thumb_size, Image.Resampling.BILINEAR)
                    buf = io.BytesIO()
                    img.convert("RGB").save(buf, format="JPEG", quality=72)
                    return idx, buf.getvalue(), full_path
            except (ImageSizeError, Exception):
                return idx, None, full_path

        to_process = [(i, full_path) for i, full_path in enumerate(selected)]
        results: list[Optional[tuple[bytes, str]]] = [None] * len(to_process)
        with ThreadPoolExecutor(
            max_workers=min(8, len(to_process)),
        ) as ex:
            futures = {
                ex.submit(_process_one_bmp, item): item[0]
                for item in to_process
            }
            for future in as_completed(futures):
                idx, thumb_bytes, full_path = future.result()
                if thumb_bytes:
                    results[idx] = (thumb_bytes, full_path)

        thumbnails = [r[0] for r in results if r is not None]
        paths = [r[1] for r in results if r is not None]
        return TaskPreviewLoadResult(
            len(all_bmps), thumbnails, paths, all_bmps, metadata,
            sources, selected_txt_name,
        )
    except Exception as ex:
        print(f"プレビュー読み込みエラー: {ex}")
        return empty


def extract_preview_thumbnails(
    zip_path: str,
    task_prefix: Optional[str] = None,
    max_images: Optional[int] = 12,
    thumb_size: tuple[int, int] = (160, 160),
) -> tuple[int, list[bytes], list[str]]:
    """タスクファイルから代表画像サムネイルを取得（zip 内を直接読み取り）。"""
    result = load_task_file_preview(
        zip_path, task_prefix, max_images, thumb_size,
    )
    return result.total_bmp_count, result.thumbnail_bytes, result.thumbnail_paths


def extract_viewer_bmp_from_zip(
    zip_path: str,
    bmp_path_in_zip: str,
) -> Optional[ViewerImageAsset]:
    """zip 内 BMP をリサイズせず一時ファイルへ書き出し、寸法と共に返す。"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            raw = read_zip_member(zf, bmp_path_in_zip)
            img = open_image_from_bytes(raw)
            width, height = img.size
            fd, tmp_path = tempfile.mkstemp(suffix=".bmp")
            os.close(fd)
            with open(tmp_path, "wb") as out:
                out.write(raw)
            return ViewerImageAsset(
                temp_path=tmp_path,
                width=width,
                height=height,
            )
    except (ImageSizeError, Exception):
        return None


def extract_viewer_bmp_from_path(bmp_path: str) -> Optional[ViewerImageAsset]:
    """ファイルシステム上の BMP を一時ファイルへコピーし、寸法と共に返す。"""
    if not bmp_path or not os.path.isfile(bmp_path):
        return None
    try:
        with open_image_file(bmp_path) as img:
            width, height = img.size
        fd, tmp_path = tempfile.mkstemp(suffix=".bmp")
        os.close(fd)
        shutil.copy2(bmp_path, tmp_path)
        return ViewerImageAsset(
            temp_path=tmp_path,
            width=width,
            height=height,
        )
    except (ImageSizeError, Exception):
        return None


def _copy_bmp_bytes_to_path(dest_path: str, data: bytes) -> None:
    dest_dir = os.path.dirname(dest_path)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    with open(dest_path, "wb") as out:
        out.write(data)


def _copy_bmp_file_to_path(src_path: str, dest_path: str) -> None:
    dest_dir = os.path.dirname(dest_path)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    if os.path.abspath(src_path) == os.path.abspath(dest_path):
        return
    shutil.copy2(src_path, dest_path)


def save_viewer_bmp_to_path(
    dest_path: str,
    *,
    temp_bmp_path: Optional[str] = None,
    zip_path: Optional[str] = None,
    bmp_path_in_zip: Optional[str] = None,
    source_bmp_path: Optional[str] = None,
) -> Optional[str]:
    """表示中の原寸 BMP を dest_path へ保存する。成功時は None。"""
    dest = (dest_path or "").strip()
    if not dest:
        return "保存先が指定されていません。"

    try:
        if temp_bmp_path and os.path.isfile(temp_bmp_path):
            _copy_bmp_file_to_path(temp_bmp_path, dest)
            return None

        if zip_path and bmp_path_in_zip:
            with zipfile.ZipFile(zip_path, "r") as zf:
                raw = read_zip_member(zf, bmp_path_in_zip)
            open_image_from_bytes(raw)
            _copy_bmp_bytes_to_path(dest, raw)
            return None

        if source_bmp_path and os.path.isfile(source_bmp_path):
            with open_image_file(source_bmp_path):
                pass
            _copy_bmp_file_to_path(source_bmp_path, dest)
            return None
    except (ImageSizeError, OSError, zipfile.BadZipFile) as ex:
        return f"画像の保存に失敗しました: {ex}"
    except Exception as ex:
        return f"画像の保存に失敗しました: {ex}"

    return "保存する画像がありません。"


_DEFAULT_SAVE_TEMPLATES = {
    "template1": "{comment}_{index}",
    "template2": "{comment}_{tool}",
    "template3": "{original}",
}


def _same_preview_bmp(path: str, bmp_path: str) -> bool:
    if not path or not bmp_path:
        return False
    if path.replace("\\", "/") == bmp_path.replace("\\", "/"):
        return True
    return os.path.basename(path).lower() == os.path.basename(bmp_path).lower()


def load_preview_tool_comments_from_folder(img_folder: str) -> list[str]:
    """img フォルダの親にある cammaster_seq.log からツール名を取得する。"""
    if not img_folder:
        return []
    log_path = os.path.join(os.path.dirname(img_folder), "cammaster_seq.log")
    return save_task_images_CamNum_selection.parse_cammaster_log_ordered(log_path)


def load_preview_tool_comments_from_zip(
    zip_path: str,
    task_prefix: Optional[str] = None,
) -> list[str]:
    """タスクファイル内の cammaster_seq.log からツール名を取得する。"""
    if not zip_path or not os.path.isfile(zip_path):
        return []
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            raw_names = zip_ref.namelist()
            normalized_names = [name.replace("\\", "/") for name in raw_names]
            norm_to_raw = _normalized_to_raw_map(raw_names, normalized_names)
            img_prefix = _find_img_prefix(normalized_names, task_prefix)
            candidates: list[str] = []
            if img_prefix and img_prefix.endswith("img/"):
                candidates.append(img_prefix[: -len("img/")] + "cammaster_seq.log")
            for name in normalized_names:
                if os.path.basename(name).lower() == "cammaster_seq.log":
                    candidates.append(name)
            seen: set[str] = set()
            for candidate in candidates:
                key = candidate.lower()
                if key in seen:
                    continue
                seen.add(key)
                raw_name = norm_to_raw.get(candidate)
                if raw_name is None:
                    for norm, raw in norm_to_raw.items():
                        if norm.lower() == key:
                            raw_name = raw
                            break
                if not raw_name:
                    continue
                raw = read_zip_member(
                    zip_ref, raw_name, max_bytes=MAX_ZIP_TEXT_BYTES,
                )
                tools = (
                    save_task_images_CamNum_selection.parse_cammaster_log_ordered_text(
                        raw.decode("utf-8", errors="ignore"),
                    )
                )
                if tools:
                    return tools
    except (OSError, zipfile.BadZipFile, Exception):
        return []
    return []


def build_preview_save_filename(
    bmp_path: str,
    sources: list[TaskImageSource],
    *,
    selected_txt_name: Optional[str] = None,
    filename_templates: Optional[dict] = None,
    tool_comments: Optional[list[str]] = None,
) -> str:
    """OK 保存と同じテンプレートで、プレビュー1枚の保存ファイル名を作る。"""
    file_name = os.path.basename(bmp_path or "")
    if not file_name:
        return "image.bmp"

    templates = filename_templates or dict(_DEFAULT_SAVE_TEMPLATES)
    matches: list[tuple[TaskImageSource, int]] = []
    for source in sources or []:
        for index, path in enumerate(source.bmp_paths, 1):
            if _same_preview_bmp(path, bmp_path):
                matches.append((source, index))

    selected: Optional[TaskImageSource] = None
    index = 1
    if matches:
        if selected_txt_name:
            wanted = selected_txt_name.lower()
            for source, idx in matches:
                if source.txt_name.lower() == wanted:
                    selected, index = source, idx
                    break
        if selected is None:
            selected, index = matches[0]

    if selected is None:
        stem, ext = os.path.splitext(file_name)
        return file_name if ext.lower() == ".bmp" else f"{stem or 'image'}.bmp"

    cam_div = save_task_images_CamNum_selection.find_cam_and_div(file_name)
    cam = cam_div[0] if len(cam_div) > 0 else ""
    div = cam_div[1] if len(cam_div) > 1 else ""
    tool_comment = None
    if tool_comments and 0 <= index - 1 < len(tool_comments):
        tool_comment = tool_comments[index - 1]

    # プレビューの「名前を付けて保存」は1枚だけなので、一括保存用の
    # 重複コメント接尾辞 (_{file} = 参照txt名のタイムスタンプ) は付けない。
    new_name = save_task_images_CamNum_selection.generate_new_file_name(
        {
            "comment": selected.comment,
            "fileName": os.path.splitext(selected.txt_name)[0],
        },
        file_name,
        index,
        tool_comment,
        cam,
        div,
        templates,
        False,
    )
    if not new_name:
        new_name = os.path.splitext(file_name)[0] or "image"
    return f"{new_name}.bmp"


def resolve_preview_save_filename(
    bmp_path: str,
    sources: list[TaskImageSource],
    *,
    selected_txt_name: Optional[str] = None,
    zip_path: Optional[str] = None,
    img_folder: Optional[str] = None,
    task_prefix: Optional[str] = None,
    filename_templates: Optional[dict] = None,
) -> str:
    """プレビュー保存用の初期ファイル名を、ツールコメント込みで解決する。"""
    tool_comments: list[str] = []
    if img_folder:
        tool_comments = load_preview_tool_comments_from_folder(img_folder)
    elif zip_path:
        tool_comments = load_preview_tool_comments_from_zip(zip_path, task_prefix)
    return build_preview_save_filename(
        bmp_path,
        sources,
        selected_txt_name=selected_txt_name,
        filename_templates=filename_templates,
        tool_comments=tool_comments,
    )


def extract_task_folder_metadata(task_dir: str) -> TaskZipMetadata:
    """viscotech/ver.txt と {task_dir}/info.txt から TaskZipMetadata を組み立てる。"""
    viscotech_root = os.path.dirname(os.path.dirname(os.path.dirname(task_dir)))
    version: Optional[str] = None
    last_from_ver: Optional[str] = None
    ver_path = os.path.join(viscotech_root, "ver.txt")
    if os.path.isfile(ver_path):
        try:
            with open(ver_path, "rb") as ver_file:
                raw_ver = ver_file.read(65536).decode("utf-8", errors="ignore")
            version = parse_task_version_text(raw_ver)
            last_from_ver = datetime_from_path(ver_path)
        except OSError:
            pass

    title, comment, last_from_info = resolve_task_folder_metadata(task_dir)
    last_updated = last_from_info or last_from_ver
    return TaskZipMetadata(
        version=version,
        title=title or None,
        comment=comment or None,
        last_updated=last_updated or None,
    )


def datetime_from_path(path: str) -> Optional[str]:
    """ファイルの更新日時を表示用文字列で返す。"""
    try:
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return None


def load_folder_preview(
    img_folder: str,
    task_dir: Optional[str] = None,
    max_images: Optional[int] = 12,
    thumb_size: tuple[int, int] = (160, 160),
    txt_name: Optional[str] = None,
) -> TaskPreviewLoadResult:
    """img フォルダからプレビュー用サムネイルと全 BMP 一覧を取得する。"""
    empty = TaskPreviewLoadResult(0, [], [], [], None)
    try:
        sources = list_task_image_sources_from_folder(img_folder)
        all_bmps, selected_txt_name = _resolve_preview_source_bmps(
            sources,
            txt_name,
            lambda: extract_ordered_bmp_paths_from_folder(img_folder),
        )
        metadata = (
            extract_task_folder_metadata(task_dir)
            if task_dir
            else None
        )
        selected = pick_sample_paths(all_bmps, max_images)
        if not selected:
            return TaskPreviewLoadResult(
                len(all_bmps), [], [], all_bmps, metadata,
                sources, selected_txt_name,
            )

        def _process_one_bmp(args):
            idx, full_path = args
            try:
                with open_image_file(full_path) as img:
                    img.thumbnail(thumb_size, Image.Resampling.BILINEAR)
                    buf = io.BytesIO()
                    img.convert("RGB").save(buf, format="JPEG", quality=72)
                    return idx, buf.getvalue(), full_path
            except (ImageSizeError, Exception):
                return idx, None, full_path

        to_process = [(i, full_path) for i, full_path in enumerate(selected)]
        results: list[Optional[tuple[bytes, str]]] = [None] * len(to_process)
        with ThreadPoolExecutor(
            max_workers=min(8, len(to_process)),
        ) as ex:
            futures = {
                ex.submit(_process_one_bmp, item): item[0]
                for item in to_process
            }
            for future in as_completed(futures):
                idx, thumb_bytes, full_path = future.result()
                if thumb_bytes:
                    results[idx] = (thumb_bytes, full_path)

        thumbnails = [r[0] for r in results if r is not None]
        paths = [r[1] for r in results if r is not None]
        return TaskPreviewLoadResult(
            len(all_bmps), thumbnails, paths, all_bmps, metadata,
            sources, selected_txt_name,
        )
    except Exception as ex:
        print(f"フォルダプレビュー読み込みエラー: {ex}")
        return empty


def save_large_image_from_zip_path(
    zip_path: str,
    bmp_path_in_zip: str,
    max_size: tuple[int, int] = (880, 640),
) -> Optional[str]:
    """zip 内の指定 BMP を一時 JPEG として書き出し、パスを返す。"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            raw = read_zip_member(zf, bmp_path_in_zip)
            img = open_image_from_bytes(raw)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            img.convert("RGB").save(tmp_path, "JPEG", quality=88)
            return tmp_path
    except (ImageSizeError, Exception):
        return None


def save_large_image_from_zip(
    zip_path: str,
    bmp_names: list[str],
    bmp_index: int,
    max_size: tuple[int, int] = (880, 640),
) -> Optional[str]:
    """zip から画像を取得し一時 JPEG ファイルのパスを返す。"""
    if not bmp_names or bmp_index < 0 or bmp_index >= len(bmp_names):
        return None
    return save_large_image_from_zip_path(
        zip_path, bmp_names[bmp_index], max_size,
    )


def prepare_option2_extraction(
    task_file: str,
    output_folder: str,
    task_folders: list[TaskFolder],
    last_loaded_file: str,
    selected_task_prefix: Optional[str],
    save_target_mode: str,
    selected_save_prefixes: set[str],
) -> dict:
    """
    Option2 用: タスクファイル展開結果を返す。

    Returns:
        img_folder_path, task_save_jobs, cleanup_paths, error のキーを持つ dict
    """
    result: dict = {
        "img_folder_path": None,
        "task_save_jobs": None,
        "cleanup_paths": [],
        "error": None,
        "status": "タスクファイルを展開中...",
    }

    try:
        folders = task_folders
        if last_loaded_file != task_file:
            folders = list_task_folders_with_metadata(task_file)

        multi_task = len(folders) > 1
        if multi_task:
            target_folders = folders
            if save_target_mode == "selected":
                target_folders = [
                    folder for folder in folders
                    if folder.prefix in selected_save_prefixes
                ]
            if not target_folders:
                result["error"] = "保存対象タスクを選択してください。"
                return result

            extract_task_file(
                task_file,
                output_folder,
                task_prefixes=[folder.prefix for folder in target_folders],
            )
            result["cleanup_paths"] = [
                os.path.join(output_folder, "viscotech"),
            ]
            task_save_jobs = []
            for folder in target_folders:
                img_path = os.path.join(
                    output_folder,
                    folder.prefix.replace("/", os.sep),
                    "img",
                )
                if os.path.exists(img_path):
                    task_save_jobs.append({
                        "label": folder.label,
                        "img_folder_path": img_path,
                        "output_folder": task_output_folder(
                            output_folder, folder,
                        ),
                    })
            if task_save_jobs:
                result["task_save_jobs"] = task_save_jobs
                found_img_path = task_save_jobs[0]["img_folder_path"]
            else:
                found_img_path = None
        else:
            found_img_path = extract_task_file(
                task_file,
                output_folder,
                selected_task_prefix,
            )
            result["cleanup_paths"] = [
                os.path.join(output_folder, "viscotech"),
            ]

        if not found_img_path:
            result["error"] = "imgフォルダが見つかりませんでした。"
        else:
            result["img_folder_path"] = found_img_path

    except Exception as ex:
        result["error"] = f"処理中にエラーが発生しました: {ex}"

    return result


def run_image_processing_jobs(
    task_save_jobs: list[dict],
    img_folder_path: str,
    output_folder: str,
    save_mode: str,
    save_cam: str,
    compression: int,
    selected_cam_list: Optional[list],
    filename_templates: dict,
    processing_state: dict,
    on_progress: Callable[[int, int, str], None],
    cleanup_paths: list[str],
) -> None:
    """
    画像保存・圧縮ジョブを実行する（バックグラウンドスレッドから呼び出す）。

    processing_state の completed / error / cancelled / is_processing 等を更新する。
  """
    if not task_save_jobs:
        task_save_jobs = [
            {
                "label": "",
                "img_folder_path": img_folder_path,
                "output_folder": output_folder,
            },
        ]

    def check_cancelled():
        return processing_state["cancelled"]

    try:
        for job_index, job in enumerate(task_save_jobs, 1):
            if processing_state["cancelled"]:
                print("処理スレッド: キャンセルされました")
                return

            job_label = job.get("label") or f"task{job_index}"
            job_img_folder = job["img_folder_path"]
            job_output_folder = job["output_folder"]
            os.makedirs(job_output_folder, exist_ok=True)

            def job_progress(current, total, message,
                             label=job_label, index=job_index):
                on_progress(
                    current,
                    total,
                    f"[{index}/{len(task_save_jobs)} {label}] {message}",
                )

            print(f"画像処理開始: {job_label} -> {job_output_folder}")
            save_task_images_CamNum_selection.process_images(
                job_img_folder, job_output_folder, save_mode, save_cam,
                preselected_cam_list=selected_cam_list,
                progress_callback=job_progress,
                filename_templates=filename_templates,
                cancel_check=check_cancelled,
            )

            if processing_state["cancelled"]:
                print("処理スレッド: キャンセルされました")
                return

            if 0 < compression < 100:
                print(f"圧縮処理開始: {job_label}")
                convert_bmp_to_jpeg(
                    job_output_folder, compression,
                    progress_callback=job_progress,
                    cancel_check=check_cancelled,
                )

                if processing_state["cancelled"]:
                    print("処理スレッド: 圧縮中にキャンセルされました")
                    return

                print(f"圧縮処理完了: {job_label}")

        print("画像処理完了")
        print("処理スレッド: completed = True を設定")
        processing_state["completed"] = True

    except Exception as ex:
        if processing_state["cancelled"]:
            print("処理スレッド: キャンセルによる中断")
            return

        print("=" * 50)
        print("エラーが発生しました:")
        traceback.print_exc()
        print("=" * 50)

        processing_state["error"] = f"{type(ex).__name__}: {ex}"

    finally:
        if processing_state.get("completed") and cleanup_paths:
            cleanup_extracted_task_folders(cleanup_paths, on_progress)

        current_files = snapshot_output_files(output_folder)
        new_files = current_files - processing_state.get("existing_files", set())
        processing_state["created_files"] = list(new_files)
        print(f"新しく作成されたファイル: {len(new_files)}件")

        print(
            f"処理スレッド終了: completed={processing_state['completed']}, "
            f"error={processing_state['error']}, "
            f"cancelled={processing_state['cancelled']}",
        )
        processing_state["is_processing"] = False
