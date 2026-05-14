import flet as ft
import os
import sys
import ctypes
import zipfile
import threading
import traceback
import time
import asyncio
import re
import io
import tempfile
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import tkinter as tk
from tkinter import filedialog

import save_task_images_CamNum_selection
from config import ConfigManager
from PIL import Image
from utils import (
    TASK_FILE_DIALOG_TYPES,
    TASK_FILE_EXTENSIONS_LABEL,
    TaskFolder,
    convert_bmp_to_jpeg,
    extract_ordered_bmp_paths_from_zip,
    extract_task_file,
    format_value,
    is_task_file_path,
    list_task_folders,
    list_task_folders_with_metadata,
)

# Windows タスクバーで独自アイコンを表示するための AppUserModelID 設定
if sys.platform == "win32":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "viscotech.taskimagesaver.1.0"
    )


# ---------------------------------------------------------------------------
# モジュールレベルのユーティリティ関数
# ---------------------------------------------------------------------------

def _resolve_resource_path(filename: str) -> str | None:
    """PyInstaller exe / 開発環境の両方でリソースファイルのパスを解決する"""
    candidates = []
    base_meipass = getattr(sys, "_MEIPASS", None)
    if base_meipass:
        candidates.append(os.path.join(base_meipass, filename))
    exe_dir = os.path.dirname(sys.executable)
    candidates.append(os.path.join(exe_dir, "_internal", filename))
    candidates.append(os.path.join(exe_dir, filename))
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(_script_dir, filename))
    for p in candidates:
        if p and os.path.exists(p):
            return os.path.abspath(p)
    return None


def _set_window_icon_win32(window_title: str, ico_path: str):
    """Win32 API でウィンドウのタイトルバー・タスクバーアイコンを直接設定する"""
    if sys.platform != "win32" or not ico_path:
        return

    from ctypes import wintypes

    user32 = ctypes.windll.user32

    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
    ]
    user32.SetClassLongPtrW.restype = ctypes.c_size_t
    user32.SetClassLongPtrW.argtypes = [
        wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t,
    ]
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
    ]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM,
    )

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1
    GCLP_HICON = -14
    GCLP_HICONSM = -34
    SM_CXSMICON = 49
    SM_CYSMICON = 50

    def _find_process_windows():
        pid = os.getpid()
        hwnds = []

        @WNDENUMPROC
        def cb(hwnd, _):
            wpid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value == pid and user32.IsWindowVisible(hwnd):
                hwnds.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        return hwnds

    def _apply_icon(hwnds, hicon_small, hicon_big):
        for hwnd in hwnds:
            if hicon_small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
                user32.SetClassLongPtrW(hwnd, GCLP_HICONSM, hicon_small)
            if hicon_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
                user32.SetClassLongPtrW(hwnd, GCLP_HICON, hicon_big)

    def apply():
        time.sleep(1.5)
        hwnds = _find_process_windows()
        if not hwnds:
            hwnd = user32.FindWindowW(None, window_title)
            if hwnd:
                hwnds = [hwnd]
        if not hwnds:
            print("Window not found for icon setting")
            return

        sm_cx = user32.GetSystemMetrics(SM_CXSMICON) or 16
        sm_cy = user32.GetSystemMetrics(SM_CYSMICON) or 16
        hicon_small = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, sm_cx, sm_cy, LR_LOADFROMFILE,
        )
        hicon_big = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, 48, 48, LR_LOADFROMFILE,
        )
        print(f"Icon handles: small={hicon_small} ({sm_cx}x{sm_cy}), big={hicon_big}")
        print(f"Target windows: {len(hwnds)}")

        _apply_icon(hwnds, hicon_small, hicon_big)

        for delay in (1.0, 2.0):
            time.sleep(delay)
            _apply_icon(hwnds, hicon_small, hicon_big)

    threading.Thread(target=apply, daemon=True).start()


def _select_folder_dialog():
    """tkinterでフォルダ選択ダイアログを表示"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder = filedialog.askdirectory(title="フォルダを選択")
    root.destroy()
    return folder


def _select_file_dialog():
    """tkinterでファイル選択ダイアログを表示"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file = filedialog.askopenfilename(
        title="タスクファイルを選択",
        filetypes=TASK_FILE_DIALOG_TYPES
    )
    root.destroy()
    return file


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

OPTION_DESCRIPTIONS = {
    "option1": (
        "現在の選択:\n\nVTV9000上のタスクから\n(オフラインPC)"
        "\n\n━━━━━━━━━━━━━\n\n"
        "オフライン上にインストールされているVTV-9000内のタスクに格納されている"
        "画像ファイルを任意のオプションで保存します。\n\n"
        "タスクを保存しているグループ番号とタスク番号を入力してください。"
    ),
    "option2": (
        "現在の選択:\n\nタスクファイルから\n(ziq, zit, zii, zig, zia)"
        "\n\n━━━━━━━━━━━━━\n\n"
        "タスクファイル(ziq, zit, zii, zig, zia)に格納されている"
        "画像ファイルを任意のオプションで保存します。\n\n"
        "画像が格納されているタスクファイルを選択してください。"
    ),
    "option3": (
        "現在の選択:\n\nVTV9000上のタスクから\n(共有VTV)"
        "\n\n━━━━━━━━━━━━━\n\n"
        "ネットワーク上にインストールされているVTV-9000内のタスクに格納されている"
        "画像ファイルを任意のオプションで保存します。\n\n"
        "共有しているVTV-9000の「viscotech」フォルダを選択してください。\n"
        "また共有VTV-900側の画像を保存しているグループ番号とタスク番号を入力してください。"
    ),
}

# ---------------------------------------------------------------------------
# アプリケーションクラス
# ---------------------------------------------------------------------------

class TaskImageSaverApp:
    """タスク画像保存アプリケーション"""

    _ALLOWED_PLACEHOLDERS = {"comment", "tool", "original", "cam", "div", "index", "file"}
    _PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z0-9_]+)(?::[^{}]+)?\}")

    def __init__(self, page: ft.Page):
        self.page = page
        self.config_manager = ConfigManager()
        self.app_state = {'is_dialog_open': False}
        self._processing_state = {}
        self._current_img_folder = ""
        self._current_output_folder = ""
        self._current_task_save_jobs = []
        self._current_cleanup_paths = []
        self._progress_dialog = None
        self._active_dialog = None

        self._file_thumbnails = []
        self._file_thumbnail_count = 0
        self._preview_zip_path = ""
        self._preview_bmp_names = []
        self._last_option2_loaded_file = ""
        self._option2_task_folders: list[TaskFolder] = []
        self._option2_selected_task_prefix = None
        self._option2_save_task_prefixes = set()

        self._init_refs()
        self._setup_page()
        self._build_ui()
        self._update_dynamic_content()

    # ==================================================================
    # 初期化
    # ==================================================================

    def _init_refs(self):
        """UI コントロールの Ref を初期化"""
        self.selected_option = ft.Ref[ft.RadioGroup]()
        self.folder_path = ft.Ref[ft.TextField]()
        self.file_path = ft.Ref[ft.TextField]()
        self.option2_group_dropdown = ft.Ref[ft.Dropdown]()
        self.option2_task_dropdown = ft.Ref[ft.Dropdown]()
        self.option2_save_mode_radio = ft.Ref[ft.RadioGroup]()
        self.option2_task_selection_column = ft.Ref[ft.Column]()
        self.option2_save_selection_info = ft.Ref[ft.Text]()
        self.group_num_field = ft.Ref[ft.TextField]()
        self.task_num_field = ft.Ref[ft.TextField]()
        self.option3_folder_field = ft.Ref[ft.TextField]()
        self.warning_text = ft.Ref[ft.Text]()
        self.info_text = ft.Ref[ft.Text]()
        self.dynamic_content = ft.Ref[ft.Column]()
        self.thumbnail_row = ft.Ref[ft.Row]()
        self.thumbnail_info = ft.Ref[ft.Text]()

        # 設定ダイアログ用
        self.save_mode_ref = ft.Ref[ft.RadioGroup]()
        self.camera_mode_ref = ft.Ref[ft.RadioGroup]()
        self.compression_slider_ref = ft.Ref[ft.Slider]()
        self.compression_label_ref = ft.Ref[ft.Text]()

        # テンプレート用
        self.template1_ref = ft.Ref[ft.TextField]()
        self.template2_ref = ft.Ref[ft.TextField]()
        self.template3_ref = ft.Ref[ft.TextField]()
        self.template1_preview_ref = ft.Ref[ft.Text]()
        self.template2_preview_ref = ft.Ref[ft.Text]()
        self.template3_preview_ref = ft.Ref[ft.Text]()
        self.preview_comment_ref = ft.Ref[ft.TextField]()
        self.preview_tool_capture_ref = ft.Ref[ft.TextField]()
        self.preview_tool_other_ref = ft.Ref[ft.TextField]()
        self.preview_original_ref = ft.Ref[ft.TextField]()
        self.preview_cam_ref = ft.Ref[ft.TextField]()
        self.preview_div_ref = ft.Ref[ft.TextField]()
        self.preview_index_ref = ft.Ref[ft.TextField]()
        self.preview_file_ref = ft.Ref[ft.TextField]()

        # 進捗ダイアログ用
        self.progress_bar_ref = ft.Ref[ft.ProgressBar]()
        self.progress_text_ref = ft.Ref[ft.Text]()
        self.progress_detail_ref = ft.Ref[ft.Text]()
        self.progress_dialog_ref = ft.Ref[ft.AlertDialog]()

    def _setup_page(self):
        """ページの基本設定"""
        self.page.title = "タスク画像保存フロー"
        self.page.window.width = 650
        self.page.window.height = 700
        self.page.window.min_width = 700
        self.page.window.min_height = 550
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.LIGHT

        icon_png = _resolve_resource_path("icon_image.png")
        if icon_png:
            self.page.window.icon = icon_png

        icon_ico = _resolve_resource_path("icon_image.ico")
        _set_window_icon_win32(self.page.title, icon_ico)

        self.page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.BLUE,
            font_family="Yu Gothic UI",
        )

    # ==================================================================
    # ダイアログ共通ヘルパー
    # ==================================================================

    def _add_dialog(self, dialog):
        """ダイアログを表示（既存ダイアログは閉じる）"""
        if self._active_dialog and self._active_dialog is not dialog:
            self._close_all_dialogs()
        self.page.show_dialog(dialog)
        self._active_dialog = dialog
        self.page.update()
        self.page.schedule_update()

    def _close_dialog(self, dialog):
        """ダイアログを閉じる"""
        if dialog is None:
            return
        try:
            dialog.open = False
            self.page.pop_dialog()
        except Exception as e:
            print(f"ダイアログclose更新エラー: {e}")
        # show_dialog/pop_dialog 管理外で overlay に残ったものの保険
        if dialog in self.page.overlay:
            self.page.overlay.remove(dialog)
        self.page.update()
        self.page.schedule_update()
        if self._active_dialog is dialog:
            self._active_dialog = None

    def _close_all_dialogs(self):
        """表示中の全ダイアログを閉じる"""
        while True:
            try:
                dlg = self.page.pop_dialog()
            except Exception:
                break
            if dlg is None:
                break
        # show_dialog/pop_dialog 管理外で overlay に残ったものの保険
        for d in list(self.page.overlay):
            if isinstance(d, ft.AlertDialog):
                d.open = False
                self.page.overlay.remove(d)
        self.page.update()
        self.page.schedule_update()
        self._progress_dialog = None
        self._active_dialog = None
        self.app_state['is_dialog_open'] = False

    def _show_message_dialog(self, title: str, message: str):
        """汎用メッセージダイアログ"""
        dialog = None

        def close(e):
            self._close_dialog(dialog)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[ft.TextButton("OK", on_click=close)],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._add_dialog(dialog)

    def _show_success_dialog(self, output_folder_path: str):
        """保存完了ダイアログ（フォルダを開くボタン付き）"""
        dialog = None

        def close(e):
            print("成功ダイアログ: OKクリック")
            self._close_all_dialogs()
            print(f"成功ダイアログ: 全閉後 overlay件数={len(self.page.overlay)}")

        def open_folder(e):
            print("成功ダイアログ: 保存先フォルダを開くクリック")
            path = output_folder_path
            if not path or not os.path.exists(path):
                self._show_message_dialog(
                    "エラー",
                    f"保存先フォルダが見つかりません:\n{path}")
                return

            self._close_all_dialogs()
            print(f"成功ダイアログ: 全閉後 overlay件数={len(self.page.overlay)}")
            def _open():
                try:
                    os.startfile(path)
                except Exception as ex:
                    print(f"保存先フォルダを開けませんでした: {type(ex).__name__}: {ex}")
            threading.Thread(target=_open, daemon=True).start()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("画像保存フロー"),
            content=ft.Column([
                ft.Text("画像が指定されたフォルダに保存されました。"),
                ft.Container(height=5),
                ft.Text(f"保存先: {output_folder_path}",
                        size=11, color=ft.Colors.GREY_700),
            ], tight=True, spacing=0),
            actions=[
                ft.ElevatedButton("保存先フォルダを開く", on_click=open_folder),
                ft.TextButton("OK", on_click=close),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._add_dialog(dialog)

    # ==================================================================
    # ファイル / フォルダ選択
    # ==================================================================

    def _pick_folder(self, e):
        async def _run():
            folder = await asyncio.to_thread(_select_folder_dialog)
            if folder:
                self.folder_path.current.value = folder
                self.warning_text.current.value = ""
                self.page.update()
        self.page.run_task(_run)

    def _pick_file(self, e):
        async def _run():
            file = await asyncio.to_thread(_select_file_dialog)
            if file:
                await self._set_option2_task_file(file)
        self.page.run_task(_run)

    @staticmethod
    def _is_task_file_path(file_path: str) -> bool:
        return is_task_file_path(file_path)

    async def _set_option2_task_file(self, file_path: str):
        """Option2 のタスクファイル選択後の共通処理（参照/ドロップ共通）"""
        if not self._is_task_file_path(file_path):
            self.warning_text.current.value = (
                f"対応拡張子は {TASK_FILE_EXTENSIONS_LABEL} のみです"
            )
            self.page.update()
            return

        self.file_path.current.value = file_path
        self.warning_text.current.value = ""
        self._show_thumbnail_loading()
        self.page.update()

        task_folders = await asyncio.to_thread(
            list_task_folders_with_metadata, file_path)
        self._option2_task_folders = task_folders
        self._option2_selected_task_prefix = (
            task_folders[0].prefix if task_folders else None
        )
        self._option2_save_task_prefixes = {
            folder.prefix for folder in task_folders
        }
        self._update_option2_task_selector_controls()
        self._update_option2_save_task_controls()

        total, thumbnails, bmp_names = await asyncio.to_thread(
            self._extract_preview_thumbnails,
            file_path,
            self._option2_selected_task_prefix,
        )
        self._file_thumbnails = thumbnails
        self._file_thumbnail_count = total
        self._preview_zip_path = file_path
        self._preview_bmp_names = bmp_names
        self._last_option2_loaded_file = file_path
        self._update_thumbnail_display()
        self.page.update()

    def _option2_group_labels(self):
        labels = []
        for folder in self._option2_task_folders:
            group = self._task_folder_group(folder)
            if group and group not in labels:
                labels.append(group)
        return labels

    def _option2_task_labels_for_group(self, group: str):
        return [
            self._task_folder_task(folder)
            for folder in self._option2_task_folders
            if self._task_folder_group(folder) == group
        ]

    def _task_folder_group(self, folder: TaskFolder) -> str:
        group, _, _task = folder.label.partition("/")
        return group

    def _task_folder_task(self, folder: TaskFolder) -> str:
        _group, _sep, task = folder.label.partition("/")
        return task

    def _selected_option2_task_folder(self):
        for folder in self._option2_task_folders:
            if folder.prefix == self._option2_selected_task_prefix:
                return folder
        return None

    def _selected_option2_save_task_folders(self):
        if not self._option2_task_folders:
            return []

        mode_control = self.option2_save_mode_radio.current
        save_mode = mode_control.value if mode_control else "all"
        if save_mode != "selected":
            return list(self._option2_task_folders)

        selected_prefixes = self._option2_save_task_prefixes
        return [
            folder for folder in self._option2_task_folders
            if folder.prefix in selected_prefixes
        ]

    def _dropdown_options(self, values):
        return [ft.dropdown.Option(value) for value in values]

    def _update_option2_task_selector_controls(self):
        group_control = self.option2_group_dropdown.current
        task_control = self.option2_task_dropdown.current
        if not group_control or not task_control:
            self._update_option2_save_task_controls()
            return

        groups = self._option2_group_labels()
        selected = next(
            (
                folder for folder in self._option2_task_folders
                if folder.prefix == self._option2_selected_task_prefix
            ),
            None,
        )
        selected_group = self._task_folder_group(selected) if selected else ""
        if not selected_group and groups:
            selected_group = groups[0]

        tasks = self._option2_task_labels_for_group(selected_group)
        selected_task = self._task_folder_task(selected) if selected else ""
        if selected_task not in tasks:
            selected_task = tasks[0] if tasks else ""

        group_control.options = self._dropdown_options(groups)
        group_control.value = selected_group
        group_control.disabled = len(groups) <= 1
        task_control.options = self._dropdown_options(tasks)
        task_control.value = selected_task
        task_control.disabled = len(tasks) <= 1
        self._update_option2_save_task_controls()

    def _option2_save_mode(self):
        control = self.option2_save_mode_radio.current
        return control.value if control else "all"

    def _update_option2_save_task_controls(self):
        selection_column = self.option2_task_selection_column.current
        info_control = self.option2_save_selection_info.current
        if not selection_column:
            return

        selection_column.controls.clear()
        folders = self._option2_task_folders
        if len(folders) <= 1:
            selection_column.controls.append(
                ft.Text("複数タスクを含むファイルで利用できます。",
                        size=11, color=ft.Colors.GREY_500)
            )
            if info_control:
                info_control.value = ""
            return

        save_mode = self._option2_save_mode()
        if save_mode != "selected":
            selection_column.controls.append(
                ft.Text("全タスク保存中です。行クリックでサムネイルを確認できます。",
                        size=11, color=ft.Colors.GREY_600)
            )

        current_prefix = self._option2_selected_task_prefix
        for folder in folders:
            is_current = folder.prefix == current_prefix
            group = self._task_folder_group(folder)
            task = self._task_folder_task(folder)
            title = folder.title or "タイトルなし"
            comment = folder.comment or ""
            has_images = folder.image_count > 0
            image_status = (
                f"画像 {folder.image_count}枚" if has_images else "画像なし")
            image_status_color = (
                ft.Colors.GREEN_700 if has_images else ft.Colors.RED_700)
            selection_column.controls.append(
                ft.Container(
                    bgcolor=(
                        ft.Colors.BLUE_50 if is_current else ft.Colors.WHITE
                    ),
                    border=ft.border.all(
                        1,
                        ft.Colors.BLUE_200
                        if is_current else ft.Colors.GREY_200,
                    ),
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=6, vertical=4),
                    ink=True,
                    on_click=lambda e, task_folder=folder:
                        self._select_option2_task_folder(task_folder),
                    content=ft.Row([
                        ft.Checkbox(
                            value=(
                                folder.prefix
                                in self._option2_save_task_prefixes
                            ),
                            disabled=(save_mode != "selected"),
                            on_change=(
                                lambda e, task_folder=folder:
                                self._on_option2_save_task_changed(
                                    task_folder, e.control.value)
                            ),
                        ),
                        ft.Text(group, width=42, size=11,
                                weight=ft.FontWeight.W_500),
                        ft.Text(task, width=32, size=11),
                        ft.Text(
                            image_status,
                            width=64,
                            size=11,
                            color=image_status_color,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Column([
                            ft.Text(
                                title, size=12,
                                weight=ft.FontWeight.W_500,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                comment, size=11,
                                color=ft.Colors.GREY_700,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ], spacing=0, expand=True),
                    ], spacing=4,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                )
            )

        if info_control:
            selected_count = len(self._selected_option2_save_task_folders())
            total_count = len(folders)
            info_control.value = (
                f"保存対象: {selected_count} / {total_count} タスク")

    def _select_option2_task_folder(self, folder):
        self.page.run_task(self._load_option2_task_preview, folder.prefix)

    def _on_option2_save_mode_changed(self, e):
        if e.control.value == "all":
            self._option2_save_task_prefixes = {
                folder.prefix for folder in self._option2_task_folders
            }
        elif not self._option2_save_task_prefixes:
            selected = self._selected_option2_task_folder()
            if selected:
                self._option2_save_task_prefixes = {selected.prefix}
        self._update_option2_save_task_controls()
        self.page.update()

    def _on_option2_save_task_changed(self, folder, value):
        if value:
            self._option2_save_task_prefixes.add(folder.prefix)
        else:
            self._option2_save_task_prefixes.discard(folder.prefix)
        self._update_option2_save_task_controls()
        self.page.update()
        if value:
            self._select_option2_task_folder(folder)

    def _set_option2_group_task_checked(self, checked: bool):
        for folder in self._option2_task_folders:
            if checked:
                self._option2_save_task_prefixes.add(folder.prefix)
            else:
                self._option2_save_task_prefixes.discard(folder.prefix)
        self._update_option2_save_task_controls()
        self.page.update()

    def _on_option2_group_changed(self, e):
        group = e.control.value
        tasks = self._option2_task_labels_for_group(group)
        task_control = self.option2_task_dropdown.current
        if task_control:
            task_control.options = self._dropdown_options(tasks)
            task_control.value = tasks[0] if tasks else ""
            task_control.disabled = len(tasks) <= 1
        self._update_option2_save_task_controls()
        self.page.update()
        self.page.run_task(self._reload_option2_selected_task_preview)

    def _on_option2_task_changed(self, e):
        self.page.run_task(self._reload_option2_selected_task_preview)

    async def _reload_option2_selected_task_preview(self):
        selected = self._selected_option2_task_folder()
        if not selected or selected.prefix == self._option2_selected_task_prefix:
            self._update_option2_save_task_controls()
            self.page.update()
            return
        await self._load_option2_task_preview(selected.prefix)

    async def _load_option2_task_preview(self, task_prefix):
        selected = next(
            (
                folder for folder in self._option2_task_folders
                if folder.prefix == task_prefix
            ),
            None,
        )
        if not selected:
            return
        self._option2_selected_task_prefix = selected.prefix
        self._update_option2_save_task_controls()
        self._show_thumbnail_loading()
        self.page.update()

        file_path = self.file_path.current.value if self.file_path.current else ""
        total, thumbnails, bmp_names = await asyncio.to_thread(
            self._extract_preview_thumbnails,
            file_path,
            self._option2_selected_task_prefix,
        )
        self._file_thumbnails = thumbnails
        self._file_thumbnail_count = total
        self._preview_zip_path = file_path
        self._preview_bmp_names = bmp_names
        self._update_thumbnail_display()
        self._update_option2_save_task_controls()
        self.page.update()

    def _save_large_image_to_temp(self, bmp_index):
        """zipから画像を取得し一時ファイルに保存してパスを返す"""
        bmp_names = self._preview_bmp_names
        try:
            with zipfile.ZipFile(self._preview_zip_path, 'r') as zf:
                with zf.open(bmp_names[bmp_index]) as img_data:
                    img = Image.open(io.BytesIO(img_data.read()))
                    img.thumbnail((460, 370), Image.LANCZOS)
                    fd, tmp_path = tempfile.mkstemp(suffix='.jpg')
                    os.close(fd)
                    img.convert('RGB').save(tmp_path, 'JPEG', quality=85)
                    return tmp_path
        except Exception:
            return None

    def _show_enlarged_image(self, index):
        """サムネイルクリック時にzipから拡大画像を取得してダイアログ表示する"""
        if not self._file_thumbnails or not self._preview_zip_path:
            return

        bmp_names = self._preview_bmp_names
        if not bmp_names:
            return

        tmp_path = self._save_large_image_to_temp(index)
        if not tmp_path:
            return

        state = {"idx": index, "tmp": tmp_path}
        dialog = None
        img_ref = ft.Ref[ft.Image]()
        counter_ref = ft.Ref[ft.Text]()

        def update_view():
            i = state["idx"]
            old_tmp = state.get("tmp")
            new_tmp = self._save_large_image_to_temp(i)
            if new_tmp and img_ref.current:
                img_ref.current.src = new_tmp
                state["tmp"] = new_tmp
            if counter_ref.current:
                counter_ref.current.value = (
                    f"{i + 1} / {len(bmp_names)}")
            self.page.update()
            if old_tmp and old_tmp != new_tmp:
                try:
                    os.remove(old_tmp)
                except OSError:
                    pass

        def on_prev(e):
            state["idx"] = (state["idx"] - 1) % len(bmp_names)
            update_view()

        def on_next(e):
            state["idx"] = (state["idx"] + 1) % len(bmp_names)
            update_view()

        def on_close(e):
            self.page.pop_dialog()
            tmp = state.get("tmp")
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

        total = len(bmp_names)
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("画像プレビュー", size=16,
                          weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=480, height=420,
                content=ft.Column([
                    ft.Container(
                        expand=True,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Image(
                            ref=img_ref,
                            src=tmp_path,
                            width=460, height=370,
                        ),
                    ),
                    ft.Row([
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            on_click=on_prev,
                            disabled=(total <= 1)),
                        ft.Text(
                            ref=counter_ref,
                            value=f"{index + 1} / {total}",
                            size=13, weight=ft.FontWeight.W_500),
                        ft.IconButton(
                            icon=ft.Icons.ARROW_FORWARD,
                            on_click=on_next,
                            disabled=(total <= 1)),
                    ], alignment=ft.MainAxisAlignment.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                   spacing=5),
            ),
            actions=[ft.TextButton("閉じる", on_click=on_close)],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    def _extract_preview_thumbnails(self, zip_path, task_prefix=None, max_images=6,
                                     thumb_size=(100, 100)):
        """タスクファイルから選択タスクの代表画像サムネイルを取得する。
        ファイルを展開せずにzip内を直接読み取る。並列処理で高速化。"""
        thumbnails = []
        bmp_names_out = []
        total = 0

        def _process_one_bmp(args):
            """1枚のBMPをサムネイル化（並列実行用）"""
            idx, full_path = args
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    with zf.open(full_path) as img_data:
                        img = Image.open(io.BytesIO(img_data.read()))
                        img.thumbnail(thumb_size, Image.BILINEAR)
                        buf = io.BytesIO()
                        img.convert('RGB').save(buf, format='JPEG', quality=65)
                        return (idx, buf.getvalue(), full_path)
            except Exception:
                return (idx, None, full_path)

        try:
            ordered_bmps = extract_ordered_bmp_paths_from_zip(zip_path, task_prefix)
            total = len(ordered_bmps)
            if not ordered_bmps:
                return total, thumbnails, bmp_names_out

            step = max(1, len(ordered_bmps) // max_images)
            selected = ordered_bmps[::step][:max_images]
            to_process = [(i, full_path) for i, full_path in enumerate(selected)]

            if not to_process:
                return total, thumbnails, bmp_names_out

            # 並列でサムネイル生成（最大6スレッド）
            results = [None] * len(to_process)
            with ThreadPoolExecutor(max_workers=min(6, len(to_process))) as ex:
                futures = {ex.submit(_process_one_bmp, item): item[0]
                          for item in to_process}
                for future in as_completed(futures):
                    idx, thumb_bytes, full_path = future.result()
                    if thumb_bytes:
                        results[idx] = (thumb_bytes, full_path)

            thumbnails = [r[0] for r in results if r is not None]
            bmp_names_out = [r[1] for r in results if r is not None]

        except Exception as ex:
            print(f"サムネイル取得エラー: {ex}")
        return total, thumbnails, bmp_names_out

    def _show_thumbnail_loading(self):
        """サムネイル領域にローディング表示をセットする"""
        row = self.thumbnail_row.current
        if not row:
            return
        row.controls.clear()
        row.alignment = ft.MainAxisAlignment.CENTER
        row.controls.append(
            ft.Row([
                ft.ProgressRing(width=16, height=16, stroke_width=2),
                ft.Text("プレビュー読み込み中...",
                        size=11, color=ft.Colors.GREY_500),
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER)
        )

    def _load_file_thumbnails(self, file_path):
        """選択されたタスクファイルの代表画像サムネイルを読み込んで表示"""
        total, thumbnails, bmp_names = self._extract_preview_thumbnails(
            file_path, self._option2_selected_task_prefix)
        self._file_thumbnails = thumbnails
        self._file_thumbnail_count = total
        self._preview_zip_path = file_path
        self._preview_bmp_names = bmp_names
        self._update_thumbnail_display()

    def _task_output_folder(self, base_output_folder: str, folder: TaskFolder) -> str:
        group = self._task_folder_group(folder)
        task = self._task_folder_task(folder)
        return os.path.join(base_output_folder, group, task)

    def _is_multi_task_file(self) -> bool:
        return len(self._option2_task_folders) > 1

    def _update_thumbnail_display(self):
        """サムネイル行コントロールを現在のキャッシュで更新する"""
        row = self.thumbnail_row.current
        info = self.thumbnail_info.current
        if not row:
            return

        row.controls.clear()
        if self._file_thumbnails:
            row.alignment = ft.MainAxisAlignment.START
            for i, img_bytes in enumerate(self._file_thumbnails):
                row.controls.append(
                    ft.Container(
                        content=ft.Image(
                            src=img_bytes, width=100, height=100,
                        ),
                        border=ft.border.all(1, ft.Colors.GREY_300),
                        border_radius=6, padding=2,
                        bgcolor=ft.Colors.WHITE,
                        on_click=lambda e, idx=i: self._show_enlarged_image(idx),
                        ink=True,
                    )
                )
        else:
            row.alignment = ft.MainAxisAlignment.CENTER
            if self._file_thumbnail_count == 0 and info:
                row.controls.append(
                    ft.Text("画像が見つかりませんでした",
                            size=11, color=ft.Colors.GREY_400, italic=True)
                )

        if info:
            if self._file_thumbnail_count > 0:
                info.value = (
                    f"代表画像プレビュー"
                    f" ({self._file_thumbnail_count}枚の画像を検出):")
            else:
                info.value = "代表画像プレビュー:"

    def _pick_option3_folder(self, e):
        async def _run():
            folder = await asyncio.to_thread(_select_folder_dialog)
            if folder:
                self.option3_folder_field.current.value = folder
                self.config_manager.set("option3_folder", folder)
                self.config_manager.save()
                self.page.update()
        self.page.run_task(_run)

    # ==================================================================
    # 動的コンテンツ（ラジオ切替で表示変更）
    # ==================================================================

    def _update_dynamic_content(self, e=None):
        option = (self.selected_option.current.value
                  if self.selected_option.current else "option1")
        self.info_text.current.value = OPTION_DESCRIPTIONS.get(option, "")
        self.dynamic_content.current.controls.clear()
        self._file_thumbnails = []
        self._file_thumbnail_count = 0
        self._preview_zip_path = ""
        self._preview_bmp_names = []
        self._option2_task_folders = []
        self._option2_selected_task_prefix = None
        self._option2_save_task_prefixes = set()
        self._current_task_save_jobs = []
        self._current_cleanup_paths = []

        if option == "option1":
            self.dynamic_content.current.controls.extend(
                self._build_group_task_fields())
        elif option == "option2":
            self.dynamic_content.current.controls.extend(
                self._build_option2_fields())
        elif option == "option3":
            self.dynamic_content.current.controls.extend(
                self._build_option3_fields())
        self.page.update()

    def _build_group_task_fields(self):
        """グループ番号・タスク番号入力フィールドを生成"""
        return [
            ft.Row([
                ft.Text("グループ番号:", width=100, size=14),
                ft.TextField(
                    ref=self.group_num_field, expand=True, hint_text="例: 1",
                    border_radius=6, text_size=13,
                    content_padding=ft.padding.only(
                        left=10, right=10, top=6, bottom=6),
                ),
                ft.Container(width=93),
            ]),
            ft.Row([
                ft.Text("タスク番号:", width=100, size=14),
                ft.TextField(
                    ref=self.task_num_field, expand=True, hint_text="例: 1",
                    border_radius=6, text_size=13,
                    content_padding=ft.padding.only(
                        left=10, right=10, top=6, bottom=6),
                ),
                ft.Container(width=93),
            ]),
        ]

    def _build_option2_fields(self):
        thumbnail_controls = []
        for i, img_bytes in enumerate(self._file_thumbnails):
            thumbnail_controls.append(
                ft.Container(
                    content=ft.Image(
                        src=img_bytes, width=100, height=100,
                    ),
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=6, padding=2,
                    bgcolor=ft.Colors.WHITE,
                    on_click=lambda e, idx=i: self._show_enlarged_image(idx),
                    ink=True,
                )
            )

        if not thumbnail_controls:
            thumbnail_controls.append(
                ft.Text("ファイルを選択すると代表画像が表示されます",
                        size=11, color=ft.Colors.GREY_400, italic=True)
            )

        info_text = "代表画像プレビュー:"
        if self._file_thumbnail_count > 0:
            info_text = (
                f"代表画像プレビュー"
                f" ({self._file_thumbnail_count}枚の画像を検出):")

        return [
            ft.Text("ファイル選択 (ziq, zit, zii, zig, zia)", size=14),
            ft.Row([
                ft.TextField(
                    ref=self.file_path, expand=True,
                    hint_text="タスクファイルを選択...",
                    border_radius=6, text_size=14,
                    content_padding=ft.padding.only(
                        left=10, right=10, top=6, bottom=6),
                ),
                ft.ElevatedButton(
                    "参照", icon=ft.Icons.FOLDER_OPEN,
                    on_click=self._pick_file),
            ]),
            ft.Text(
                "※ タスク一覧の行をクリックすると、確認用サムネイルが更新されます。",
                size=11, color=ft.Colors.GREY_600),
            ft.Container(
                bgcolor=ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.GREY_200),
                border_radius=8,
                padding=10,
                content=ft.Column([
                    ft.Text("保存対象タスク", size=13,
                            weight=ft.FontWeight.W_500),
                    ft.RadioGroup(
                        ref=self.option2_save_mode_radio,
                        value="all",
                        on_change=self._on_option2_save_mode_changed,
                        content=ft.Row([
                            ft.Radio(value="all", label="全タスク"),
                            ft.Radio(value="selected", label="選択したタスクのみ"),
                        ], spacing=4),
                    ),
                    ft.Row([
                        ft.TextButton(
                            "全選択",
                            on_click=lambda e:
                                self._set_option2_group_task_checked(True)),
                        ft.TextButton(
                            "全解除",
                            on_click=lambda e:
                                self._set_option2_group_task_checked(False)),
                    ], spacing=0),
                    ft.Text(
                        ref=self.option2_save_selection_info,
                        value="", size=11, color=ft.Colors.GREY_700),
                    ft.Column(
                        ref=self.option2_task_selection_column,
                        controls=[
                            ft.Text("タスクファイルを選択してください。",
                                    size=11, color=ft.Colors.GREY_500)
                        ],
                        spacing=0,
                        height=260,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ], spacing=4),
            ),
            ft.Container(height=5),
            ft.Text(
                ref=self.thumbnail_info, value=info_text,
                size=12, color=ft.Colors.GREY_700),
            ft.Container(
                content=ft.Row(
                    ref=self.thumbnail_row,
                    controls=thumbnail_controls,
                    spacing=8, wrap=True,
                    alignment=(
                        ft.MainAxisAlignment.CENTER
                        if not self._file_thumbnails
                        else ft.MainAxisAlignment.START),
                ),
                height=120,
                border=ft.border.all(1, ft.Colors.GREY_200),
                border_radius=8, padding=8,
                bgcolor=ft.Colors.GREY_50,
                alignment=ft.Alignment(0, 0),
            ),
        ]

    def _build_option3_fields(self):
        fields = self._build_group_task_fields()
        fields.extend([
            ft.Container(height=5),
            ft.Text("共有VTVフォルダ選択:", size=14),
            ft.Row([
                ft.TextField(
                    ref=self.option3_folder_field, expand=True,
                    value=self.config_manager.get("option3_folder", ""),
                    hint_text="viscotechフォルダを選択...",
                    border_radius=6, text_size=13,
                    content_padding=ft.padding.only(
                        left=10, right=10, top=6, bottom=6),
                ),
                ft.ElevatedButton(
                    "参照", icon=ft.Icons.FOLDER_OPEN,
                    on_click=self._pick_option3_folder),
            ]),
        ])
        return fields

    # ==================================================================
    # テンプレートヘルパー
    # ==================================================================

    def _extract_unknown_placeholders(self, template: str):
        if not template:
            return []
        names = {m.group(1) for m in self._PLACEHOLDER_PATTERN.finditer(str(template))}
        return sorted(n for n in names if n not in self._ALLOWED_PLACEHOLDERS)

    @staticmethod
    def _parse_int_from_textfield(tf: ft.TextField, default_value: int):
        if tf is None:
            return default_value
        raw = (tf.value or "").strip()
        if raw == "":
            tf.error_text = None
            return default_value
        try:
            tf.error_text = None
            return int(raw)
        except Exception:
            tf.error_text = "数値を入力してください"
            return default_value

    def _build_preview(self, template: str, condition: int):
        """テンプレートのプレビュー文字列を生成（condition: 1/2/3）"""
        sample_comment = (
            self.preview_comment_ref.current.value
            if self.preview_comment_ref.current else "ng") or "ng"
        sample_tool_capture = (
            self.preview_tool_capture_ref.current.value
            if self.preview_tool_capture_ref.current else "画像取込01") or "画像取込01"
        sample_tool_other = (
            self.preview_tool_other_ref.current.value
            if self.preview_tool_other_ref.current else "ToolA") or "ToolA"
        sample_original = (
            self.preview_original_ref.current.value
            if self.preview_original_ref.current
            else "260120115606036_1_1") or "260120115606036_1_1"
        sample_cam = self._parse_int_from_textfield(
            self.preview_cam_ref.current, 1)
        sample_div = self._parse_int_from_textfield(
            self.preview_div_ref.current, 2)
        sample_index = self._parse_int_from_textfield(
            self.preview_index_ref.current, 3)
        sample_file = (
            self.preview_file_ref.current.value
            if self.preview_file_ref.current
            else "260120115606036") or "260120115606036"

        tool_value = sample_tool_capture if condition == 1 else sample_tool_other
        comment_value = sample_comment if condition in (1, 2) else ""

        try:
            return save_task_images_CamNum_selection.apply_filename_template(
                template=template or "",
                comment=comment_value,
                tool_comment=tool_value,
                original_name=sample_original,
                cam=sample_cam,
                div=sample_div,
                index=sample_index,
                file_source=sample_file,
            )
        except Exception:
            return ""

    def _refresh_template_previews(self):
        """テンプレートプレビューとバリデーションを更新"""
        if not (self.template1_ref.current and self.template2_ref.current
                and self.template3_ref.current):
            return

        t1 = self.template1_ref.current.value or ""
        t2 = self.template2_ref.current.value or ""
        t3 = self.template3_ref.current.value or ""

        for tf, template in (
            (self.template1_ref.current, t1),
            (self.template2_ref.current, t2),
            (self.template3_ref.current, t3),
        ):
            unknown = self._extract_unknown_placeholders(template)
            if unknown:
                tf.error_text = ("未対応のプレースホルダー: "
                                 + ", ".join(f"{{{n}}}" for n in unknown))
            else:
                tf.error_text = None

        if self.template1_preview_ref.current:
            self.template1_preview_ref.current.value = (
                f"プレビュー: {self._build_preview(t1, 1)}.bmp")
        if self.template2_preview_ref.current:
            self.template2_preview_ref.current.value = (
                f"プレビュー: {self._build_preview(t2, 2)}.bmp")
        if self.template3_preview_ref.current:
            self.template3_preview_ref.current.value = (
                f"プレビュー: {self._build_preview(t3, 3)}.bmp")

        self.page.update()

    def _on_template_change(self, e):
        self._refresh_template_previews()

    def _build_template_section(self, preview_original_default: str):
        """出力ファイル名テンプレートの ExpansionTile を構築"""
        on_change = self._on_template_change

        return ft.ExpansionTile(
            title=ft.Text("出力ファイル名テンプレート",
                          size=13, weight=ft.FontWeight.W_500),
            expanded=False,
            controls_padding=ft.Padding(left=10, right=10, top=0, bottom=10),
            controls=[
                ft.Container(
                    bgcolor=ft.Colors.GREY_50, padding=10, border_radius=8,
                    content=ft.Column([
                        # 条件1
                        ft.Text("条件1: コメントあり + 画像取込XX形式",
                                size=11, color=ft.Colors.GREY_700),
                        ft.TextField(
                            ref=self.template1_ref, value="{comment}_{index}",
                            dense=True, text_size=12,
                            content_padding=ft.padding.symmetric(
                                horizontal=10, vertical=8),
                            on_change=on_change,
                        ),
                        ft.Text(ref=self.template1_preview_ref,
                                value="プレビュー: ",
                                size=10, color=ft.Colors.GREY_700),
                        ft.Container(height=4),
                        # 条件2
                        ft.Text("条件2: コメントあり + その他のツールコメント",
                                size=11, color=ft.Colors.GREY_700),
                        ft.TextField(
                            ref=self.template2_ref, value="{comment}_{tool}",
                            dense=True, text_size=12,
                            content_padding=ft.padding.symmetric(
                                horizontal=10, vertical=8),
                            on_change=on_change,
                        ),
                        ft.Text(ref=self.template2_preview_ref,
                                value="プレビュー: ",
                                size=10, color=ft.Colors.GREY_700),
                        ft.Container(height=4),
                        # 条件3
                        ft.Text("条件3: コメントなし",
                                size=11, color=ft.Colors.GREY_700),
                        ft.TextField(
                            ref=self.template3_ref, value="{original}",
                            dense=True, text_size=12,
                            content_padding=ft.padding.symmetric(
                                horizontal=10, vertical=8),
                            on_change=on_change,
                        ),
                        ft.Text(ref=self.template3_preview_ref,
                                value="プレビュー: ",
                                size=10, color=ft.Colors.GREY_700),
                        ft.Container(height=8),
                        # プレースホルダー説明
                        ft.Container(
                            bgcolor=ft.Colors.BLUE_50, padding=8,
                            border_radius=4,
                            content=ft.Column([
                                ft.Text("使用可能なプレースホルダー:",
                                        size=10, weight=ft.FontWeight.W_500),
                                ft.Text("{comment} - 画像コメント", size=10),
                                ft.Text("{tool} - ツールコメント", size=10),
                                ft.Text("{original} - 元ファイル名", size=10),
                                ft.Text("{cam} - カメラ番号", size=10),
                                ft.Text("{div} - DIV番号（列番号）", size=10),
                                ft.Text("{index} - 連番", size=10),
                                ft.Text("{file} - 参照元テキストファイル名",
                                        size=10),
                            ], spacing=2),
                        ),
                        ft.Container(height=8),
                        # プレビュー用サンプル値
                        ft.Container(
                            bgcolor=ft.Colors.GREY_100, padding=8,
                            border_radius=6,
                            content=ft.Column([
                                ft.Text(
                                    "プレビュー用サンプル値"
                                    "（変更するとプレビューが更新されます）",
                                    size=10, weight=ft.FontWeight.W_500,
                                    color=ft.Colors.GREY_800,
                                ),
                                ft.Row([
                                    ft.TextField(
                                        ref=self.preview_comment_ref,
                                        label="comment", value="ng",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                    ft.TextField(
                                        ref=self.preview_original_ref,
                                        label="original",
                                        value=preview_original_default,
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                ], spacing=8),
                                ft.Row([
                                    ft.TextField(
                                        ref=self.preview_tool_capture_ref,
                                        label="tool(画像取込)",
                                        value="画像取込01",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                    ft.TextField(
                                        ref=self.preview_tool_other_ref,
                                        label="tool(その他)", value="ToolA",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                ], spacing=8),
                                ft.Row([
                                    ft.TextField(
                                        ref=self.preview_cam_ref,
                                        label="cam", value="1",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                    ft.TextField(
                                        ref=self.preview_div_ref,
                                        label="div", value="2",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                    ft.TextField(
                                        ref=self.preview_index_ref,
                                        label="index", value="3",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                ], spacing=8),
                                ft.Row([
                                    ft.TextField(
                                        ref=self.preview_file_ref,
                                        label="file（参照元テキストファイル名）",
                                        value="260120115606036",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                ], spacing=8),
                            ], spacing=6),
                        ),
                    ], spacing=4),
                ),
            ],
        )

    # ==================================================================
    # 設定ダイアログ
    # ==================================================================

    def _update_compression_label(self, e):
        if self.compression_slider_ref.current and self.compression_label_ref.current:
            value = int(self.compression_slider_ref.current.value)
            self.compression_label_ref.current.value = f"現在の値: {value}"
            self.page.update()

    def _show_settings_dialog(
        self,
        img_folder_path: str,
        output_folder: str,
        task_save_jobs=None,
        cleanup_paths=None,
    ):
        """設定ダイアログを表示"""
        self.app_state['is_dialog_open'] = True
        self._current_img_folder = img_folder_path
        self._current_output_folder = output_folder
        self._current_task_save_jobs = task_save_jobs or []
        self._current_cleanup_paths = cleanup_paths or []

        now = datetime.now()
        preview_original_default = (
            f"{now.strftime('%y%m%d%H%M%S')}{now.microsecond // 1000:03d}")

        self._processing_state = {
            'is_processing': False, 'current': 0, 'total': 0,
            'message': '準備中...', 'completed': False, 'error': None,
            'started': False, 'cancelled': False, 'created_files': [],
            'output_folder': '', 'existing_files': set(),
        }

        settings_dialog = None

        def on_ok(e):
            save_mode = self.save_mode_ref.current.value
            save_cam = self.camera_mode_ref.current.value
            compression = int(self.compression_slider_ref.current.value)
            filename_templates = {
                'template1': (self.template1_ref.current.value
                              if self.template1_ref.current
                              else "{comment}_{index}"),
                'template2': (self.template2_ref.current.value
                              if self.template2_ref.current
                              else "{comment}_{tool}"),
                'template3': (self.template3_ref.current.value
                              if self.template3_ref.current
                              else "{original}"),
            }
            self._close_dialog(settings_dialog)

            if save_cam == "1":
                self._show_camera_selection_dialog(
                    save_mode, compression, filename_templates)
            else:
                self._execute_image_processing(
                    save_mode, "0", compression, None, filename_templates)

        def on_cancel(e):
            self._close_dialog(settings_dialog)
            self.app_state['is_dialog_open'] = False

        settings_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("保存設定", size=18, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=420,
                content=ft.Column([
                    ft.Text("保存モード", size=13, weight=ft.FontWeight.W_500),
                    ft.Container(
                        bgcolor=ft.Colors.GREY_50, padding=10, border_radius=8,
                        content=ft.RadioGroup(
                            ref=self.save_mode_ref, value="0",
                            content=ft.Column([
                                ft.Radio(value="0", label="全ての画像を保存"),
                                ft.Radio(value="1",
                                         label="コメント付き画像を保存"),
                                ft.Radio(value="2", label="ロック画像を保存"),
                            ], spacing=2),
                        ),
                    ),
                    ft.Container(height=8),

                    ft.Text("カメラ列保存モード",
                            size=13, weight=ft.FontWeight.W_500),
                    ft.Container(
                        bgcolor=ft.Colors.GREY_50, padding=10, border_radius=8,
                        content=ft.RadioGroup(
                            ref=self.camera_mode_ref, value="0",
                            content=ft.Column([
                                ft.Radio(value="0", label="全てのカメラ列"),
                                ft.Radio(value="1",
                                         label="保存するカメラ列を選択"),
                            ], spacing=2),
                        ),
                    ),
                    ft.Container(height=8),

                    ft.Text("圧縮率を選択 (100は元画像(bmp)で保存)",
                            size=13, weight=ft.FontWeight.W_500),
                    ft.Container(
                        bgcolor=ft.Colors.GREY_50, padding=10, border_radius=8,
                        content=ft.Column([
                            ft.Slider(
                                ref=self.compression_slider_ref,
                                min=10, max=100, divisions=9, value=100,
                                label="{value}",
                                on_change=self._update_compression_label,
                            ),
                            ft.Row([
                                ft.Text("10", size=11),
                                ft.Container(expand=True),
                                ft.Text("100", size=11),
                            ]),
                            ft.Text(
                                ref=self.compression_label_ref,
                                value="現在の値: 100", size=11,
                                color=ft.Colors.GREY_700,
                            ),
                        ], spacing=2),
                    ),
                    ft.Container(height=8),

                    self._build_template_section(preview_original_default),
                ], scroll=ft.ScrollMode.AUTO, spacing=5),
            ),
            actions=[
                ft.ElevatedButton(
                    "OK", bgcolor=ft.Colors.BLUE,
                    color=ft.Colors.WHITE, on_click=on_ok),
                ft.OutlinedButton("キャンセル", on_click=on_cancel),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._add_dialog(settings_dialog)
        self._refresh_template_previews()

    # ==================================================================
    # カメラ選択ダイアログ
    # ==================================================================

    def _show_camera_selection_dialog(self, save_mode, compression,
                                     filename_templates):
        """カメラ選択ダイアログを表示"""
        camera_arrays = save_task_images_CamNum_selection.get_camera_list(
            self._current_img_folder)

        if not camera_arrays:
            self._show_message_dialog("エラー",
                                     "カメラリストを取得できませんでした。")
            return

        labels_dict = defaultdict(list)
        for key, value in camera_arrays:
            labels_dict[key].append(value)
        label_params = [f"カメラ {key}" for key in labels_dict.keys()]
        checkbox_params = [values for values in labels_dict.values()]

        selected_items = {i: checkbox_params[i][:]
                         for i in range(len(checkbox_params))}
        checkbox_refs_dict = {i: [] for i in range(len(checkbox_params))}

        def on_checkbox_change(label_index, item, value):
            if value:
                if item not in selected_items[label_index]:
                    selected_items[label_index].append(item)
            else:
                if item in selected_items[label_index]:
                    selected_items[label_index].remove(item)

        def select_all(label_index):
            selected_items[label_index] = checkbox_params[label_index][:]
            for cb in checkbox_refs_dict[label_index]:
                cb.value = True
            self.page.update()

        def deselect_all(label_index):
            selected_items[label_index] = []
            for cb in checkbox_refs_dict[label_index]:
                cb.value = False
            self.page.update()

        camera_dialog = None

        def on_ok(e):
            result_list = []
            for i, items in selected_items.items():
                for item in items:
                    result_list.append([i + 1, item])
            self._close_dialog(camera_dialog)
            self._execute_image_processing(
                save_mode, "1", compression, result_list, filename_templates)

        def on_cancel(e):
            self._close_dialog(camera_dialog)
            self.app_state['is_dialog_open'] = False

        camera_columns = []
        for i, (label_text, items) in enumerate(
                zip(label_params, checkbox_params)):
            checkboxes = []
            for item in items:
                cb = ft.Checkbox(
                    label=str(item), value=True,
                    on_change=lambda e, idx=i, itm=item:
                        on_checkbox_change(idx, itm, e.control.value),
                )
                checkbox_refs_dict[i].append(cb)
                checkboxes.append(cb)

            camera_container = ft.Container(
                bgcolor=ft.Colors.GREY_100, border_radius=8,
                padding=10, width=150,
                content=ft.Column([
                    ft.Text(label_text, size=13, weight=ft.FontWeight.W_500),
                    ft.Divider(height=1),
                    ft.Row([
                        ft.TextButton(
                            "全選択",
                            on_click=lambda e, idx=i: select_all(idx)),
                        ft.TextButton(
                            "解除",
                            on_click=lambda e, idx=i: deselect_all(idx)),
                    ], spacing=0),
                    ft.Column(checkboxes, scroll=ft.ScrollMode.AUTO,
                              height=200, spacing=0),
                ], spacing=5),
            )
            camera_columns.append(camera_container)

        camera_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("カメラ・列番号選択",
                          size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=min(len(camera_columns) * 160, 600),
                content=ft.Column([
                    ft.Text("保存したいカメラ番号、列番号を選択してください",
                            size=12),
                    ft.Container(height=5),
                    ft.Row(camera_columns,
                           scroll=ft.ScrollMode.AUTO, spacing=10),
                ]),
            ),
            actions=[
                ft.ElevatedButton(
                    "OK", bgcolor=ft.Colors.BLUE,
                    color=ft.Colors.WHITE, on_click=on_ok),
                ft.OutlinedButton("キャンセル", on_click=on_cancel),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._add_dialog(camera_dialog)

    # ==================================================================
    # 進捗管理 & 画像処理
    # ==================================================================

    def _snapshot_output_files(self, output_folder):
        """出力先配下のファイルを相対パスで取得する。"""
        existing_files = set()
        if not os.path.exists(output_folder):
            return existing_files
        for walk_root, _dirs, files in os.walk(output_folder):
            for file_name in files:
                full_path = os.path.join(walk_root, file_name)
                existing_files.add(os.path.relpath(full_path, output_folder))
        return existing_files

    def _cleanup_extracted_task_folders(self, cleanup_paths):
        """タスクファイル展開時に作成した作業フォルダを削除する。"""
        for cleanup_path in cleanup_paths:
            if not cleanup_path or not os.path.isdir(cleanup_path):
                continue
            try:
                entries = []
                for walk_root, dirs, files in os.walk(cleanup_path, topdown=False):
                    for file_name in files:
                        entries.append(os.path.join(walk_root, file_name))
                    for dir_name in dirs:
                        entries.append(os.path.join(walk_root, dir_name))
                entries.append(cleanup_path)

                total = len(entries)
                self._update_progress(
                    0, total, "展開フォルダを削除中...")

                for index, entry_path in enumerate(entries, 1):
                    if os.path.isfile(entry_path) or os.path.islink(entry_path):
                        os.unlink(entry_path)
                    elif os.path.isdir(entry_path):
                        os.rmdir(entry_path)

                    rel_path = os.path.relpath(entry_path, cleanup_path)
                    self._update_progress(
                        index,
                        total,
                        f"展開フォルダ削除中:\n{rel_path}",
                    )

                self._update_progress(
                    total, total, "展開フォルダ削除完了")
                print(f"展開フォルダを削除しました: {cleanup_path}")
            except Exception as ex:
                print(f"展開フォルダの削除に失敗しました: {cleanup_path} - {ex}")

    def _show_progress_dialog(self):
        """進捗ダイアログを表示"""
        def on_cancel_click(e):
            self._processing_state['cancelled'] = True
            self._processing_state['message'] = 'キャンセル中...'
            print("キャンセルボタンがクリックされました")
            if e.control:
                e.control.disabled = True
                e.control.text = "キャンセル中..."
                self.page.update()

        progress_dialog = ft.AlertDialog(
            ref=self.progress_dialog_ref,
            modal=True,
            title=ft.Text("画像処理中", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=350,
                content=ft.Column([
                    ft.Text(ref=self.progress_text_ref,
                            value="準備中...", size=13),
                    ft.Container(height=10),
                    ft.ProgressBar(
                        ref=self.progress_bar_ref,
                        value=0, width=330, bar_height=8, border_radius=4),
                    ft.Container(height=5),
                    ft.Text(ref=self.progress_detail_ref,
                            value="0 / 0 ファイル",
                            size=11, color=ft.Colors.GREY_600),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ),
            actions=[
                ft.OutlinedButton(
                    "キャンセル", on_click=on_cancel_click,
                    style=ft.ButtonStyle(color=ft.Colors.RED_700)),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
        )
        self._progress_dialog = progress_dialog
        self._add_dialog(progress_dialog)

    def _update_progress_ui(self):
        try:
            if (self.progress_bar_ref.current
                    and self.progress_text_ref.current
                    and self.progress_detail_ref.current):
                ps = self._processing_state
                total = ps['total']
                progress = ps['current'] / total if total > 0 else 0
                self.progress_bar_ref.current.value = progress
                self.progress_text_ref.current.value = ps['message']
                self.progress_detail_ref.current.value = (
                    f"{ps['current']} / {total} ファイル")
        except Exception as e:
            print(f"UI更新エラー: {e}")

    def _update_progress(self, current, total, message):
        """進捗を更新（別スレッドから呼び出される）"""
        self._processing_state['current'] = current
        self._processing_state['total'] = total
        self._processing_state['message'] = message
        print(f"進捗: {current}/{total} - {message}")

    def _close_progress_dialog(self):
        """進捗ダイアログを overlay から除去（page.update は呼び出し元で行う）"""
        self._processing_state['is_processing'] = False
        try:
            dialog = self._progress_dialog or self.progress_dialog_ref.current
            if not dialog:
                for d in self.page.overlay:
                    if isinstance(d, ft.AlertDialog):
                        title = getattr(getattr(d, "title", None), "value", "")
                        if title == "画像処理中":
                            dialog = d
                            break
            if dialog:
                self._close_dialog(dialog)
                self.progress_dialog_ref.current = None
                self._progress_dialog = None
        except Exception as e:
            print(f"ダイアログ閉じエラー(ref経由): {e}")

    def _show_cancel_confirm_dialog(self, created_files, output_folder_path):
        """キャンセル時の確認ダイアログを表示"""
        file_count = len(created_files)
        confirm_dialog = None

        def delete_files(e):
            self._close_dialog(confirm_dialog)
            deleted_count = 0
            for filename in created_files:
                fp = os.path.join(output_folder_path, filename)
                try:
                    if os.path.exists(fp):
                        os.unlink(fp)
                        deleted_count += 1
                        print(f"削除: {filename}")
                except Exception as ex:
                    print(f"削除失敗: {filename} - {ex}")
            self._show_message_dialog(
                "キャンセル完了",
                f"処理がキャンセルされました。\n{deleted_count}件のファイルを削除しました。")

        def keep_files(e):
            self._close_dialog(confirm_dialog)
            self._show_message_dialog(
                "キャンセル完了",
                f"処理がキャンセルされました。\n"
                f"{file_count}件のファイルは保存先に残っています。")

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("キャンセル確認",
                          size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=350,
                content=ft.Column([
                    ft.Text("処理がキャンセルされました。", size=13),
                    ft.Container(height=10),
                    ft.Text(f"既に {file_count} 件のファイルが保存されています。",
                            size=13),
                    ft.Container(height=5),
                    ft.Text("これらのファイルを削除しますか？",
                            size=13, weight=ft.FontWeight.W_500),
                ]),
            ),
            actions=[
                ft.ElevatedButton(
                    "削除する", bgcolor=ft.Colors.RED_600,
                    color=ft.Colors.WHITE, on_click=delete_files),
                ft.OutlinedButton("残す", on_click=keep_files),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._add_dialog(confirm_dialog)

    async def _progress_monitor_async(self):
        """進捗を監視してUIを更新する（非同期）"""
        print("監視タスク開始")
        loop_count = 0
        ps = self._processing_state

        while True:
            self._update_progress_ui()
            self.page.update()
            loop_count += 1

            if loop_count % 5 == 0:
                print(f"監視タスク: ループ{loop_count}回目 - "
                      f"is_processing={ps['is_processing']}, "
                      f"completed={ps['completed']}, error={ps['error']}")

            if not ps['is_processing']:
                print(f"監視タスク: is_processing=False を検知 - "
                      f"completed={ps['completed']}, error={ps['error']}, "
                      f"cancelled={ps['cancelled']}")
                if ps['completed'] or ps['error'] or ps['cancelled']:
                    print("監視タスク: ループを抜けます")
                    break
                else:
                    print("監視タスク: completedもerrorもcancelledも"
                          "設定されていないため、待機を継続")

            await asyncio.sleep(0.1)

        print("監視タスク: 処理完了を検知、最終処理開始")
        self._update_progress_ui()
        self.page.update()
        await asyncio.sleep(0.2)

        self._close_progress_dialog()
        await asyncio.sleep(0.1)

        if ps['cancelled']:
            print("監視タスク: キャンセル処理")
            created_files = ps.get('created_files', [])
            output_folder_path = ps.get('output_folder', '')
            if created_files and output_folder_path:
                print(f"作成されたファイル: {len(created_files)}件 "
                      "- 確認ダイアログを表示")
                self._show_cancel_confirm_dialog(
                    created_files, output_folder_path)
            else:
                self._show_message_dialog(
                    "キャンセル", "処理がキャンセルされました。")
        elif ps['error']:
            print(f"監視タスク: エラー処理 - {ps['error']}")
            self._show_message_dialog(
                "エラー",
                f"処理中にエラーが発生しました:\n{ps['error']}")
        elif ps['completed']:
            print("監視タスク: 完了処理")
            self._close_all_dialogs()
            self._show_success_dialog(ps.get('output_folder', ''))

        ps['started'] = False
        self.app_state['is_dialog_open'] = False
        print("監視タスク終了")

    def _execute_image_processing(self, save_mode, save_cam, compression,
                                  selected_cam_list, filename_templates):
        """画像処理を開始"""
        ps = self._processing_state
        img_folder_path = self._current_img_folder
        output_folder = self._current_output_folder
        cleanup_paths = list(self._current_cleanup_paths)
        task_save_jobs = self._current_task_save_jobs or [
            {
                'label': '',
                'img_folder_path': img_folder_path,
                'output_folder': output_folder,
            }
        ]

        if ps.get('started'):
            print("警告: 処理は既に開始されています。重複実行をスキップします。")
            return
        ps['started'] = True

        if filename_templates is None:
            filename_templates = {
                'template1': "{comment}_{index}",
                'template2': "{comment}_{tool}",
                'template3': "{original}",
            }

        def check_cancelled():
            return ps['cancelled']

        def run_processing():
            print(f"処理スレッド開始: {len(task_save_jobs)}タスク, "
                  f"output={output_folder}")
            try:
                for job_index, job in enumerate(task_save_jobs, 1):
                    if ps['cancelled']:
                        print("処理スレッド: キャンセルされました")
                        return

                    job_label = job.get('label') or f"task{job_index}"
                    job_img_folder = job['img_folder_path']
                    job_output_folder = job['output_folder']
                    os.makedirs(job_output_folder, exist_ok=True)

                    def job_progress(current, total, message,
                                     label=job_label, index=job_index):
                        self._update_progress(
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

                    if ps['cancelled']:
                        print("処理スレッド: キャンセルされました")
                        return

                    if 0 < compression < 100:
                        print(f"圧縮処理開始: {job_label}")
                        convert_bmp_to_jpeg(
                            job_output_folder, compression,
                            progress_callback=job_progress,
                            cancel_check=check_cancelled)

                        if ps['cancelled']:
                            print("処理スレッド: 圧縮中にキャンセルされました")
                            return

                        print(f"圧縮処理完了: {job_label}")

                print("画像処理完了")
                print("処理スレッド: completed = True を設定")
                ps['completed'] = True

            except Exception as ex:
                if ps['cancelled']:
                    print("処理スレッド: キャンセルによる中断")
                    return

                print("=" * 50)
                print("エラーが発生しました:")
                traceback.print_exc()
                print("=" * 50)

                ps['error'] = f"{type(ex).__name__}: {ex}"

            finally:
                if ps.get('completed') and cleanup_paths:
                    self._cleanup_extracted_task_folders(cleanup_paths)

                current_files = self._snapshot_output_files(output_folder)
                new_files = current_files - ps.get('existing_files', set())
                ps['created_files'] = list(new_files)
                print(f"新しく作成されたファイル: {len(new_files)}件")

                print(f"処理スレッド終了: completed={ps['completed']}, "
                      f"error={ps['error']}, cancelled={ps['cancelled']}")
                ps['is_processing'] = False

        # 状態を初期化
        ps.update({
            'is_processing': True, 'current': 0, 'total': 0,
            'message': '準備中...', 'completed': False, 'error': None,
            'cancelled': False, 'created_files': [],
            'output_folder': output_folder,
        })

        ps['existing_files'] = self._snapshot_output_files(output_folder)

        self._show_progress_dialog()

        threading.Thread(target=run_processing, daemon=True).start()
        self.page.run_task(self._progress_monitor_async)

    # ==================================================================
    # メインハンドラ
    # ==================================================================

    def _on_ok_click(self, e):
        """OKボタンクリック時の処理"""
        if self.app_state['is_dialog_open']:
            print("警告: ダイアログは既に開いています。重複クリックをスキップします。")
            return

        option = self.selected_option.current.value
        output_folder = (self.folder_path.current.value
                         if self.folder_path.current else "")

        if not output_folder:
            self.warning_text.current.value = "画像を保存するフォルダを選択してください"
            self.page.update()
            return

        if option == "option1":
            group_num = format_value(
                self.group_num_field.current.value
                if self.group_num_field.current else "")
            task_num = format_value(
                self.task_num_field.current.value
                if self.task_num_field.current else "")

            if group_num == "00" or task_num == "00":
                self.warning_text.current.value = (
                    "グループ番号とタスク番号を入力してください")
                self.page.update()
                return

            img_folder_path = (
                f"C:\\viscotech\\task\\g{group_num}\\{task_num}\\img")

            if not os.path.exists(img_folder_path):
                self.warning_text.current.value = "imgフォルダが見つかりませんでした。"
                self.page.update()
                return

            self.warning_text.current.value = ""
            self.page.update()
            self._show_settings_dialog(img_folder_path, output_folder)

        elif option == "option2":
            task_file = (self.file_path.current.value
                         if self.file_path.current else "")
            if not task_file:
                self.warning_text.current.value = "タスクファイルを選択してください"
                self.page.update()
                return

            self._handle_option2(task_file, output_folder)

        elif option == "option3":
            group_num = format_value(
                self.group_num_field.current.value
                if self.group_num_field.current else "")
            task_num = format_value(
                self.task_num_field.current.value
                if self.task_num_field.current else "")
            option3_folder = (self.option3_folder_field.current.value
                              if self.option3_folder_field.current else "")

            if group_num == "00" or task_num == "00":
                self.warning_text.current.value = (
                    "グループ番号とタスク番号を入力してください")
                self.page.update()
                return

            if not option3_folder:
                self.warning_text.current.value = (
                    "外部のviscotechフォルダを選択してください")
                self.page.update()
                return

            img_folder_path = os.path.join(
                option3_folder, f"task\\g{group_num}\\{task_num}\\img")

            if not os.path.exists(img_folder_path):
                self.warning_text.current.value = "imgフォルダが見つかりませんでした。"
                self.page.update()
                return

            self.warning_text.current.value = ""
            self.page.update()
            self._show_settings_dialog(img_folder_path, output_folder)

    def _handle_option2(self, task_file: str, output_folder: str):
        """Option2: タスクファイルの展開と設定ダイアログ表示"""
        loading_text_ref = ft.Ref[ft.Text]()
        loading_result = {
            'img_folder_path': None,
            'task_save_jobs': None,
            'cleanup_paths': [],
            'error': None,
        }
        selected_task_prefix = self._option2_selected_task_prefix
        save_target_mode = self._option2_save_mode()
        selected_save_prefixes = set(self._option2_save_task_prefixes)

        def process_task_file():
            try:
                loading_result['status'] = "タスクファイルを展開中..."
                task_folders = self._option2_task_folders
                if self._last_option2_loaded_file != task_file:
                    task_folders = list_task_folders_with_metadata(task_file)
                multi_task = len(task_folders) > 1
                if multi_task:
                    extract_task_file(task_file, output_folder)
                    loading_result['cleanup_paths'] = [
                        os.path.join(output_folder, "viscotech")
                    ]
                    target_folders = task_folders
                    if save_target_mode == "selected":
                        target_folders = [
                            folder for folder in task_folders
                            if folder.prefix in selected_save_prefixes
                        ]
                    if not target_folders:
                        loading_result['error'] = "保存対象タスクを選択してください。"
                        return

                    task_save_jobs = []
                    for folder in target_folders:
                        img_path = os.path.join(
                            output_folder,
                            folder.prefix.replace("/", os.sep),
                            "img",
                        )
                        if os.path.exists(img_path):
                            task_save_jobs.append({
                                'label': folder.label,
                                'img_folder_path': img_path,
                                'output_folder': self._task_output_folder(
                                    output_folder, folder),
                            })
                    if task_save_jobs:
                        loading_result['task_save_jobs'] = task_save_jobs
                        found_img_path = task_save_jobs[0]['img_folder_path']
                    else:
                        found_img_path = None
                else:
                    found_img_path = extract_task_file(
                        task_file,
                        output_folder,
                        selected_task_prefix,
                    )
                    loading_result['cleanup_paths'] = [
                        os.path.join(output_folder, "viscotech")
                    ]

                if not found_img_path:
                    loading_result['error'] = "imgフォルダが見つかりませんでした。"
                else:
                    loading_result['img_folder_path'] = found_img_path

            except Exception as ex:
                loading_result['error'] = (
                    f"処理中にエラーが発生しました: {ex}")

        async def process_and_continue():
            process_thread = threading.Thread(
                target=process_task_file, daemon=True)
            process_thread.start()

            while process_thread.is_alive():
                if loading_text_ref.current and loading_result.get('status'):
                    loading_text_ref.current.value = loading_result['status']
                self.page.update()
                await asyncio.sleep(0.1)

            self._close_dialog(loading_dialog)

            if loading_result['error']:
                self.warning_text.current.value = loading_result['error']
                self.app_state['is_dialog_open'] = False
                self.page.update()
            else:
                self._show_settings_dialog(
                    loading_result['img_folder_path'],
                    output_folder,
                    loading_result.get('task_save_jobs'),
                    loading_result.get('cleanup_paths'),
                )

        loading_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("タスクファイル処理中",
                          size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=300,
                content=ft.Column([
                    ft.Row([
                        ft.ProgressRing(width=20, height=20, stroke_width=2),
                        ft.Text(ref=loading_text_ref,
                                value="準備中...", size=13),
                    ], spacing=10),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ),
        )
        self._add_dialog(loading_dialog)
        self.page.run_task(process_and_continue)

    async def _on_cancel_click(self, e):
        """終了ボタンクリック時の処理"""
        self.page.window.visible = False
        self.page.update()
        await asyncio.sleep(0.2)
        os._exit(0)

    # ==================================================================
    # UI 構築
    # ==================================================================

    def _build_sidebar(self):
        return ft.Container(
            width=220,
            bgcolor=ft.Colors.GREY_100,
            padding=15,
            alignment=ft.Alignment(-1, -1),
            content=ft.Column([
                ft.Text("タスク画像保存フロー", size=18, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text(
                    ref=self.info_text,
                    value=OPTION_DESCRIPTIONS["option1"],
                    size=14,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.START,
            ),
        )

    def _build_main_content(self):
        return ft.Container(
            expand=True,
            padding=ft.padding.only(left=20, right=20, top=15, bottom=15),
            alignment=ft.Alignment(-1, -1),
            content=ft.Column([
                ##ft.Text("タスク画像保存フロー",
                ##        size=20, weight=ft.FontWeight.BOLD),
                ##ft.Container(
                #    height=2, bgcolor=ft.Colors.BLUE, border_radius=2),
                ##ft.Container(height=10),

                ft.Text("インポート先を選択",
                        size=15, weight=ft.FontWeight.W_500),
                ft.Container(
                    bgcolor=ft.Colors.GREY_50, padding=10, border_radius=8,
                    content=ft.RadioGroup(
                        ref=self.selected_option, value="option1",
                        on_change=self._update_dynamic_content,
                        content=ft.Column([
                            ft.Radio(value="option1",
                                     label="VTV9000上のタスクから (オフラインPC)"),
                            ft.Radio(value="option2",
                                     label="タスクファイルから (ziq, zit, zii, zig, zia)"),
                            ft.Radio(value="option3",
                                     label="VTV9000上のタスクから (共有VTV)"),
                        ], spacing=2),
                    ),
                ),
                ft.Container(height=8),

                ft.Text("画像を保存するフォルダを選択",
                        size=15, weight=ft.FontWeight.W_500),
                ft.Row([
                    ft.TextField(
                        ref=self.folder_path, expand=True,
                        hint_text="フォルダを選択...",
                        border_radius=8, text_size=13,
                        content_padding=ft.padding.only(
                            left=10, right=10, top=8, bottom=8),
                    ),
                    ft.ElevatedButton(
                        "参照", icon=ft.Icons.FOLDER_OPEN,
                        on_click=self._pick_folder),
                ]),

                ft.Text(ref=self.warning_text, value="",
                        color=ft.Colors.RED, size=11),
                ft.Container(height=5),

                ft.Container(
                    content=ft.Column(
                        ref=self.dynamic_content, spacing=8,
                        alignment=ft.MainAxisAlignment.START),
                ),
                ft.Container(height=10),

                ft.Row([
                    ft.ElevatedButton(
                        "OK", width=130, height=40,
                        bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE,
                        on_click=self._on_ok_click),
                    ft.OutlinedButton(
                        "終了", width=130, height=40,
                        on_click=self._on_cancel_click),
                ]),
            ],
            spacing=5,
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.START,
            ),
        )

    def _build_ui(self):
        self.page.add(
            ft.Row([
                self._build_sidebar(),
                ft.VerticalDivider(width=1),
                self._build_main_content(),
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )


def main(page: ft.Page):
    TaskImageSaverApp(page)


if __name__ == "__main__":
    ft.app(target=main)
