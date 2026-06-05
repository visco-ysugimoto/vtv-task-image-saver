"""
タスク画像保存アプリ（Flet）のエントリポイント。

UI: task_image_saver_ui
ロジック: task_image_saver_logic
リソース・ダイアログ: flet_resources

右クリックメニュー等から起動した場合、第1引数にタスクファイル (.ziq 等) の
パスが渡されます。起動時に Option2 を選択しプレビューを表示します。
"""
from __future__ import annotations

from app_runtime import ensure_ascii_runtime_exit, is_packaged_app, setup_runtime

ensure_ascii_runtime_exit()

import os
import sys
import traceback

from app_runtime import _LAUNCH_FILE_ENV, log_launch_resolution
from launch_handoff import read_and_clear_pending_launch
from utils import is_task_file_path


def resolve_launch_task_file() -> str | None:
    """コマンドラインまたはランチャー経由の環境変数からプレビュー対象パスを取得する。"""
    pending = read_and_clear_pending_launch()
    if pending and is_task_file_path(pending):
        log_launch_resolution(pending, "pending_launch.json")
        return pending

    env_path = os.environ.get(_LAUNCH_FILE_ENV, "").strip().strip('"')
    if env_path:
        candidate = os.path.abspath(env_path)
        if is_task_file_path(candidate):
            log_launch_resolution(candidate, _LAUNCH_FILE_ENV)
            return candidate

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--preview-file", "-f") and i + 1 < len(args):
            candidate = args[i + 1].strip().strip('"')
            i += 2
            if candidate and is_task_file_path(candidate):
                return os.path.abspath(candidate)
            continue
        if arg.startswith("-"):
            i += 1
            continue
        candidate = arg.strip().strip('"')
        if candidate and is_task_file_path(candidate):
            resolved = os.path.abspath(candidate)
            log_launch_resolution(resolved, "sys.argv")
            return resolved
        i += 1
    log_launch_resolution(None, "none")
    return None


def main(page) -> None:
    import flet as ft

    page.padding = 0
    page.add(
        ft.Container(
            expand=True,
            alignment=ft.Alignment(0, 0),
            content=ft.Column(
                [
                    ft.ProgressRing(width=32, height=32),
                    ft.Text(
                        "起動しています...",
                        size=13,
                        color=ft.Colors.GREY_700,
                    ),
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
    )
    page.update()

    launch_file = resolve_launch_task_file()
    page.controls.clear()

    from task_image_saver_ui import TaskImageSaverApp

    try:
        TaskImageSaverApp(page, launch_task_file=launch_file)
    except Exception as exc:
        page.add(
            ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text(
                            "起動中にエラーが発生しました",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.RED,
                        ),
                        ft.Text(str(exc), selectable=True),
                        ft.Text(
                            traceback.format_exc(),
                            size=11,
                            selectable=True,
                            font_family="Consolas",
                        ),
                        ft.Text(
                            "詳細: 同フォルダの startup.log または\n"
                            "%LOCALAPPDATA%\\VISCO\\TaskImageSaver\\console.log",
                            size=11,
                            color=ft.Colors.GREY_700,
                        ),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                ),
            )
        )


def _prefer_built_flet_client() -> None:
    """開発時のみ: flet build windows の Dropzone 入り exe を優先する。"""
    if is_packaged_app():
        return
    build_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "windows")
    if not os.path.isdir(build_dir):
        return
    for name in ("TaskImageSaver.exe", "task-image-saver.exe"):
        path = os.path.join(build_dir, name)
        if os.path.isfile(path):
            os.environ["FLET_VIEW_PATH"] = path
            return
    for name in os.listdir(build_dir):
        if name.lower().endswith(".exe"):
            os.environ["FLET_VIEW_PATH"] = os.path.join(build_dir, name)
            break


if __name__ == "__main__":
    setup_runtime()
    _prefer_built_flet_client()
    import flet as ft

    ft.run(main)
