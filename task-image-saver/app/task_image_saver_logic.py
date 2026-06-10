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
from dataclasses import dataclass
from typing import Callable, Optional

import save_task_images_CamNum_selection
from PIL import Image
from security_limits import (
    ImageSizeError,
    open_image_from_bytes,
    read_zip_member,
)
from utils import (
    TaskFolder,
    TaskZipMetadata,
    convert_bmp_to_jpeg,
    extract_ordered_bmp_paths_from_zip,
    extract_task_file,
    extract_task_zip_metadata,
    list_task_folders_with_metadata,
    pick_sample_paths,
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


def load_task_file_preview(
    zip_path: str,
    task_prefix: Optional[str] = None,
    max_images: Optional[int] = 12,
    thumb_size: tuple[int, int] = (160, 160),
) -> TaskPreviewLoadResult:
    """タスクファイルからプレビュー用サムネイルと全 BMP 一覧を取得する。"""
    empty = TaskPreviewLoadResult(0, [], [], [], None)
    try:
        all_bmps = extract_ordered_bmp_paths_from_zip(zip_path, task_prefix)
        metadata = extract_task_zip_metadata(zip_path, task_prefix)
        selected = pick_sample_paths(all_bmps, max_images)
        if not selected:
            return TaskPreviewLoadResult(
                len(all_bmps), [], [], all_bmps, metadata,
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
