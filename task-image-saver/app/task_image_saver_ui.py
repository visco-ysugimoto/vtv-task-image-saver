"""
Flet によるタスク画像保存アプリの UI 層。
ビジネスロジックは task_image_saver_logic、リソースは flet_resources を参照する。
"""
import asyncio
from collections import defaultdict
import os
import threading
from datetime import datetime

import flet as ft
import save_task_images_CamNum_selection
from config import ConfigManager
from flet_dropzone_support import (
    dropzone_setup_hint,
    is_file_dropzone_available,
    should_use_file_dropzone,
    wrap_with_task_file_dropzone,
)
from flet_resources import (
    resolve_resource_path,
    select_file_dialog,
    select_folder_dialog,
    set_window_icon_win32,
)
from flet_ui_constants import (
    DEFAULT_FILENAME_TEMPLATES,
    DEFAULT_PREVIEW_LIMIT,
    OPTION_DESCRIPTIONS,
    PREVIEW_LIMIT_BOX_WIDTH,
    PREVIEW_LIMIT_OPTIONS,
    PREVIEW_LIMIT_ROW_BOTTOM_GAP,
    PREVIEW_LIMIT_ROW_HEIGHT,
    PREVIEW_LIMIT_TEXT_SIZE,
)
from task_image_saver_logic import (
    TemplatePreviewSamples,
    build_option1_img_path,
    build_option3_img_path,
    build_template_preview,
    extract_unknown_placeholders,
    filter_save_task_folders,
    find_task_folder_by_prefix,
    load_task_file_preview,
    parse_int_value,
    prepare_option2_extraction,
    run_image_processing_jobs,
    save_large_image_from_zip_path,
    snapshot_output_files,
    task_folder_group,
    task_folder_task,
    task_output_folder,
)
from utils import (
    TASK_FILE_EXTENSIONS_LABEL,
    TaskFolder,
    format_value,
    is_task_file_path,
    list_task_folders_with_metadata,
)

class TaskImageSaverApp:
    """タスク画像保存アプリケーション"""

    def __init__(
        self,
        page: ft.Page,
        *,
        launch_task_file: str | None = None,
    ):
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
        self._image_viewer_cleanup = None

        self._file_thumbnails = []
        self._file_thumbnail_count = 0
        self._preview_zip_path = ""
        self._preview_bmp_names = []
        self._option2_all_bmp_paths: list[str] = []
        self._option2_task_metadata = None
        self._preview_limit_value = DEFAULT_PREVIEW_LIMIT
        self._last_option2_loaded_file = ""
        self._option2_task_folders: list[TaskFolder] = []
        self._option2_selected_task_prefix = None
        self._option2_save_task_prefixes = set()
        self._launch_task_file = (
            launch_task_file if launch_task_file and is_task_file_path(launch_task_file)
            else None
        )

        self._init_refs()
        self._setup_page()
        self._build_ui()
        self._update_dynamic_content()
        if self._launch_task_file:
            self.page.run_task(self._bootstrap_launch_preview_async)

    # ==================================================================
    # 初期化
    # ==================================================================

    def _init_refs(self):
        """UI コントロールの Ref を初期化"""
        self.selected_option = ft.Ref[ft.RadioGroup]()
        self.folder_path = ft.Ref[ft.TextField]()
        self.file_path = ft.Ref[ft.TextField]()
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
        self.preview_limit_menu = ft.Ref[ft.PopupMenuButton]()
        self.preview_limit_value_text = ft.Ref[ft.Text]()
        self.option2_workspace = ft.Ref[ft.Container]()
        self.import_source_section = ft.Ref[ft.Container]()

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
        if self._launch_task_file:
            self.page.title = "タスク画像保存フロー - プレビュー"
            self.page.window.min_width = 900
            self.page.window.min_height = 640
        else:
            self.page.window.width = 900
            self.page.window.height = 760
            self.page.window.min_width = 820
            self.page.window.min_height = 600
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.LIGHT

        icon_png = (
            resolve_resource_path("icon.png")
            or resolve_resource_path("launcher.png")
        )
        if icon_png:
            self.page.window.icon = icon_png

        icon_ico = (
            resolve_resource_path("icon_windows.ico")
            or resolve_resource_path("launcher.ico")
        )
        set_window_icon_win32(self.page.title, icon_ico)

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
        # Flet の modal 周りは AlertDialog 以外（モーダルバリア等）も
        # overlay に残ることがあるため、ここで overlay を掃除する。
        for d in list(self.page.overlay):
            try:
                if hasattr(d, "open"):
                    d.open = False
            except Exception:
                pass
            try:
                self.page.overlay.remove(d)
            except Exception:
                pass
        self.page.update()
        self.page.schedule_update()
        self._close_image_viewer()
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

    async def _handle_dropped_task_file(self, path: str) -> None:
        """OS からウィンドウへドロップされたタスクファイルを読み込む。"""
        if not is_task_file_path(path):
            if self.warning_text.current:
                self.warning_text.current.value = (
                    f"対応拡張子は {TASK_FILE_EXTENSIONS_LABEL} のみです"
                )
            self.page.update()
            return

        if self.warning_text.current:
            self.warning_text.current.value = ""
        if self.selected_option.current:
            self.selected_option.current.value = "option2"
        self._update_dynamic_content()
        # Option2 UI 再構築後に Ref が付くまで 1 tick 待つ
        await asyncio.sleep(0)
        await self._set_option2_task_file(path)

    def _pick_folder(self, e):
        async def _run():
            folder = await asyncio.to_thread(select_folder_dialog)
            if folder and self.folder_path.current:
                self.folder_path.current.value = folder
                if self.warning_text.current:
                    self.warning_text.current.value = ""
                self.page.update()

        self.page.run_task(_run)

    def _pick_file(self, e):
        async def _run():
            file = await asyncio.to_thread(select_file_dialog)
            if file:
                await self._set_option2_task_file(file)

        self.page.run_task(_run)

    @staticmethod
    def _is_task_file_path(file_path: str) -> bool:
        return is_task_file_path(file_path)

    async def _set_option2_task_file(self, file_path: str):
        """Option2 のタスクファイル選択後の共通処理（参照/ドロップ共通）"""
        if not self._is_task_file_path(file_path):
            if self.warning_text.current:
                self.warning_text.current.value = (
                    f"対応拡張子は {TASK_FILE_EXTENSIONS_LABEL} のみです"
                )
            self.page.update()
            return

        if self.file_path.current:
            self.file_path.current.value = file_path
        if self.warning_text.current:
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
        self._update_option2_save_task_controls()
        if self.preview_limit_menu.current:
            self.preview_limit_menu.current.disabled = False

        await self._load_option2_preview_async(file_path)
        self._last_option2_loaded_file = file_path
        self.page.update()

    async def _bootstrap_launch_preview_async(self):
        """右クリック起動: Option2 を開いて初回タスクを読み込む。"""
        if not self._launch_task_file:
            return
        launch_file = self._launch_task_file
        try:
            await asyncio.sleep(0)
            if self.selected_option.current:
                self.selected_option.current.value = "option2"
            self._update_dynamic_content()
            self.page.update()
            await asyncio.sleep(0)
            await self._set_option2_task_file(launch_file)
            # 初回読み込み後は通常モード扱いに戻す。
            self._launch_task_file = None
            self.page.update()
        except Exception as exc:
            if self.warning_text.current:
                self.warning_text.current.value = (
                    f"プレビュー読み込みエラー: {exc}"
                )
            self.page.update()

    @staticmethod
    def _parse_preview_limit(value: str) -> int | None:
        if value == "すべて":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(DEFAULT_PREVIEW_LIMIT)

    def _current_preview_limit(self) -> int | None:
        raw = self._preview_limit_value
        if self.preview_limit_value_text.current:
            raw = self.preview_limit_value_text.current.value
        return self._parse_preview_limit(raw or DEFAULT_PREVIEW_LIMIT)

    def _set_preview_limit_value(self, value: str) -> None:
        self._preview_limit_value = value or DEFAULT_PREVIEW_LIMIT
        if self.preview_limit_value_text.current:
            self.preview_limit_value_text.current.value = self._preview_limit_value
        self.page.update()
        self.page.run_task(self._reload_option2_preview)

    def _apply_task_preview_result(self, file_path: str, result) -> None:
        self._file_thumbnails = result.thumbnail_bytes
        self._file_thumbnail_count = result.total_bmp_count
        self._preview_zip_path = file_path
        self._preview_bmp_names = result.thumbnail_paths
        self._option2_all_bmp_paths = result.all_bmp_paths
        self._option2_task_metadata = result.metadata
        self._update_option2_metadata_display()
        self._update_option2_save_task_controls()

    def _format_option2_meta_summary(self) -> str:
        """選択タスクのメタデータを1行にまとめる。"""
        meta = self._option2_task_metadata
        if not meta:
            return ""
        parts: list[str] = []
        if meta.version:
            parts.append(f"Ver {meta.version}")
        if meta.last_updated:
            parts.append(f"更新 {meta.last_updated}")
        return " · ".join(parts)

    def _folder_meta_line(self, folder: TaskFolder, is_current: bool) -> str:
        """リスト行用のメタ情報（Ver・更新日など）。"""
        if is_current:
            summary = self._format_option2_meta_summary()
            if summary:
                return summary
        if folder.updated_at:
            return f"更新 {folder.updated_at}"
        return ""

    def _update_option2_metadata_display(self) -> None:
        self._update_thumbnail_display()

    async def _load_option2_preview_async(self, file_path: str) -> None:
        max_images = self._current_preview_limit()
        result = await asyncio.to_thread(
            load_task_file_preview,
            file_path,
            self._option2_selected_task_prefix,
            max_images,
            (160, 160),
        )
        self._apply_task_preview_result(file_path, result)

    def _preview_limit_menu_items(self) -> list[ft.PopupMenuItem]:
        items: list[ft.PopupMenuItem] = []

        def make_handler(selected: str):
            def handler(_e):
                self._set_preview_limit_value(selected)
            return handler

        for option in PREVIEW_LIMIT_OPTIONS:
            items.append(
                ft.PopupMenuItem(
                    content=option,
                    on_click=make_handler(option),
                )
            )
        return items

    async def _reload_option2_preview(self):
        file_path = self.file_path.current.value if self.file_path.current else ""
        if not file_path:
            return
        self._show_thumbnail_loading()
        self.page.update()
        await self._load_option2_preview_async(file_path)
        self.page.update()

    def _selected_option2_task_folder(self):
        return find_task_folder_by_prefix(
            self._option2_task_folders,
            self._option2_selected_task_prefix,
        )

    def _selected_option2_save_task_folders(self):
        return filter_save_task_folders(
            self._option2_task_folders,
            self._option2_save_mode(),
            self._option2_save_task_prefixes,
        )

    def _dropdown_options(self, values):
        return [ft.dropdown.Option(value) for value in values]

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
        if not folders:
            selection_column.controls.append(
                ft.Text("タスクファイルを選択してください。",
                        size=11, color=ft.Colors.GREY_500)
            )
            if info_control:
                info_control.value = ""
            return

        save_mode = self._option2_save_mode()
        if len(folders) > 1 and save_mode != "selected":
            selection_column.controls.append(
                ft.Text("全タスク保存中です。行クリックでサムネイルを確認できます。",
                        size=11, color=ft.Colors.GREY_600)
            )

        current_prefix = self._option2_selected_task_prefix
        for folder in folders:
            is_current = folder.prefix == current_prefix
            group = task_folder_group(folder)
            task = task_folder_task(folder)
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
                    border=ft.Border.all(
                        1,
                        ft.Colors.BLUE_200
                        if is_current else ft.Colors.GREY_200,
                    ),
                    border_radius=6,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=4),
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
                                max_lines=1,
                            ),
                            *(
                                [ft.Text(
                                    self._folder_meta_line(folder, is_current),
                                    size=10,
                                    color=ft.Colors.BLUE_700,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    max_lines=1,
                                )]
                                if self._folder_meta_line(folder, is_current)
                                else []
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
        await self._load_option2_preview_async(file_path)
        self._update_option2_save_task_controls()
        self.page.update()

    def _viewer_bmp_paths(self) -> list[str]:
        return self._option2_all_bmp_paths or self._preview_bmp_names

    def _save_large_image_to_temp(
        self,
        bmp_index: int,
        *,
        max_size: tuple[int, int] = (3840, 2160),
    ):
        """zip から画像を取得し一時ファイルに保存してパスを返す"""
        paths = self._viewer_bmp_paths()
        if not paths or bmp_index < 0 or bmp_index >= len(paths):
            return None
        return save_large_image_from_zip_path(
            self._preview_zip_path,
            paths[bmp_index],
            max_size=max_size,
        )

    def _close_image_viewer(self):
        """表示中の画像プレビューオーバーレイを閉じる。"""
        cleanup = self._image_viewer_cleanup
        self._image_viewer_cleanup = None
        if cleanup:
            cleanup()

    def _show_enlarged_image(self, thumb_index: int):
        """サムネイルクリック時に zip から拡大画像を表示する"""
        if not self._preview_bmp_names or not self._preview_zip_path:
            return
        path = self._preview_bmp_names[thumb_index]
        paths = self._viewer_bmp_paths()
        try:
            start_index = paths.index(path)
        except ValueError:
            start_index = thumb_index
        self._open_image_viewer(start_index)

    def _open_image_viewer(self, start_index: int):
        bmp_paths = self._viewer_bmp_paths()
        if not bmp_paths or not self._preview_zip_path:
            return

        self._close_image_viewer()

        tmp_path = self._save_large_image_to_temp(start_index)
        if not tmp_path:
            return

        state = {
            "idx": start_index,
            "tmp": tmp_path,
            "fullscreen": False,
            "prev_window_full_screen": bool(self.page.window.full_screen),
        }
        overlay_ref = ft.Ref[ft.Container]()
        panel_ref = ft.Ref[ft.Container]()
        viewer_area_ref = ft.Ref[ft.Container]()
        viewer_ref = ft.Ref[ft.InteractiveViewer]()
        img_ref = ft.Ref[ft.Image]()
        counter_ref = ft.Ref[ft.Text]()
        name_ref = ft.Ref[ft.Text]()
        fullscreen_btn_ref = ft.Ref[ft.IconButton]()
        header_ref = ft.Ref[ft.Row]()
        footer_ref = ft.Ref[ft.Container]()

        def reset_zoom():
            if viewer_ref.current:
                viewer_ref.current.reset()

        def zoom_in(_e):
            if viewer_ref.current:
                viewer_ref.current.zoom(1.25)

        def zoom_out(_e):
            if viewer_ref.current:
                viewer_ref.current.zoom(0.8)

        def apply_layout():
            fullscreen = state["fullscreen"]
            if overlay_ref.current:
                overlay_ref.current.bgcolor = (
                    ft.Colors.BLACK
                    if fullscreen
                    else ft.Colors.with_opacity(0.45, ft.Colors.BLACK)
                )
            if panel_ref.current:
                panel_ref.current.expand = fullscreen
                panel_ref.current.width = None if fullscreen else 900
                panel_ref.current.height = None if fullscreen else 700
                panel_ref.current.bgcolor = (
                    ft.Colors.BLACK if fullscreen else ft.Colors.WHITE
                )
                panel_ref.current.border_radius = 0 if fullscreen else 8
                panel_ref.current.padding = (
                    ft.Padding.all(0)
                    if fullscreen
                    else ft.Padding.all(8)
                )
            if viewer_area_ref.current:
                viewer_area_ref.current.top = 0 if fullscreen else 44
                viewer_area_ref.current.bottom = 76 if fullscreen else 108
                viewer_area_ref.current.left = 0
                viewer_area_ref.current.right = 0
            if header_ref.current:
                header_ref.current.visible = not fullscreen
            if footer_ref.current:
                footer_ref.current.bgcolor = (
                    ft.Colors.with_opacity(0.82, ft.Colors.BLACK_87)
                    if fullscreen
                    else ft.Colors.WHITE
                )
                footer_ref.current.padding = (
                    ft.Padding.symmetric(horizontal=12, vertical=8)
                    if fullscreen
                    else ft.Padding.all(0)
                )
            if name_ref.current:
                name_ref.current.color = (
                    ft.Colors.WHITE if fullscreen else ft.Colors.GREY_700
                )
            if fullscreen_btn_ref.current:
                fullscreen_btn_ref.current.icon = (
                    ft.Icons.FULLSCREEN_EXIT
                    if fullscreen
                    else ft.Icons.FULLSCREEN
                )
                fullscreen_btn_ref.current.tooltip = (
                    "全画面を終了" if fullscreen else "全画面表示"
                )
            self.page.window.full_screen = fullscreen
            reset_zoom()
            self.page.update()

        def toggle_fullscreen(_e):
            state["fullscreen"] = not state["fullscreen"]
            apply_layout()

        def update_view():
            i = state["idx"]
            old_tmp = state.get("tmp")
            new_tmp = self._save_large_image_to_temp(i)
            if new_tmp and img_ref.current:
                img_ref.current.src = new_tmp
                state["tmp"] = new_tmp
            if counter_ref.current:
                counter_ref.current.value = f"{i + 1} / {len(bmp_paths)}"
            if name_ref.current:
                name_ref.current.value = os.path.basename(bmp_paths[i])
            reset_zoom()
            self.page.update()
            if old_tmp and old_tmp != new_tmp:
                try:
                    os.remove(old_tmp)
                except OSError:
                    pass

        def on_prev(_e):
            state["idx"] = (state["idx"] - 1) % len(bmp_paths)
            update_view()

        def on_next(_e):
            state["idx"] = (state["idx"] + 1) % len(bmp_paths)
            update_view()

        def cleanup():
            self.page.window.full_screen = state["prev_window_full_screen"]
            if overlay in self.page.overlay:
                self.page.overlay.remove(overlay)
            tmp = state.get("tmp")
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            self.page.update()

        def on_close(_e=None):
            self._close_image_viewer()

        total = len(bmp_paths)
        overlay = ft.Container(
            ref=overlay_ref,
            expand=True,
            alignment=ft.Alignment(0, 0),
            bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
            content=ft.Container(
                ref=panel_ref,
                width=900,
                height=700,
                bgcolor=ft.Colors.WHITE,
                border_radius=8,
                padding=8,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                content=ft.Stack(
                    expand=True,
                    controls=[
                        ft.Container(
                            ref=viewer_area_ref,
                            left=0,
                            right=0,
                            top=44,
                            bottom=108,
                            clip_behavior=ft.ClipBehavior.HARD_EDGE,
                            content=ft.InteractiveViewer(
                                ref=viewer_ref,
                                expand=True,
                                min_scale=0.5,
                                max_scale=8,
                                trackpad_scroll_causes_scale=True,
                                content=ft.Image(
                                    ref=img_ref,
                                    src=tmp_path,
                                    fit=ft.BoxFit.CONTAIN,
                                    expand=True,
                                ),
                            ),
                        ),
                        ft.Container(
                            ref=header_ref,
                            top=0,
                            left=0,
                            right=0,
                            bgcolor=ft.Colors.WHITE,
                            content=ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                vertical_alignment=(
                                    ft.CrossAxisAlignment.CENTER
                                ),
                                controls=[
                                    ft.Text(
                                        "画像プレビュー",
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Row(
                                        [
                                            ft.IconButton(
                                                ref=fullscreen_btn_ref,
                                                icon=ft.Icons.FULLSCREEN,
                                                tooltip="全画面表示",
                                                on_click=toggle_fullscreen,
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.CLOSE,
                                                tooltip="閉じる",
                                                on_click=on_close,
                                            ),
                                        ],
                                        spacing=0,
                                    ),
                                ],
                            ),
                        ),
                        ft.Container(
                            ref=footer_ref,
                            left=0,
                            right=0,
                            bottom=0,
                            bgcolor=ft.Colors.WHITE,
                            content=ft.Column(
                                [
                                    ft.Text(
                                        ref=name_ref,
                                        value=os.path.basename(
                                            bmp_paths[start_index]
                                        ),
                                        size=11,
                                        color=ft.Colors.GREY_700,
                                    ),
                                    ft.Row(
                                        [
                                            ft.IconButton(
                                                icon=ft.Icons.ARROW_BACK,
                                                tooltip="前の画像",
                                                on_click=on_prev,
                                                disabled=(total <= 1),
                                            ),
                                            ft.Text(
                                                ref=counter_ref,
                                                value=(
                                                    f"{start_index + 1} / {total}"
                                                ),
                                                size=13,
                                                weight=ft.FontWeight.W_500,
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.ARROW_FORWARD,
                                                tooltip="次の画像",
                                                on_click=on_next,
                                                disabled=(total <= 1),
                                            ),
                                            ft.VerticalDivider(width=12),
                                            ft.IconButton(
                                                icon=ft.Icons.ZOOM_OUT,
                                                tooltip="縮小",
                                                on_click=zoom_out,
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.ZOOM_IN,
                                                tooltip="拡大",
                                                on_click=zoom_in,
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.FIT_SCREEN,
                                                tooltip="表示をリセット",
                                                on_click=lambda _e: reset_zoom(),
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.FULLSCREEN,
                                                tooltip="全画面表示",
                                                on_click=toggle_fullscreen,
                                            ),
                                            ft.TextButton(
                                                "閉じる",
                                                on_click=on_close,
                                            ),
                                        ],
                                        alignment=ft.MainAxisAlignment.CENTER,
                                        wrap=True,
                                    ),
                                ],
                                horizontal_alignment=(
                                    ft.CrossAxisAlignment.CENTER
                                ),
                                spacing=4,
                            ),
                        ),
                    ],
                ),
            ),
        )

        self._image_viewer_cleanup = cleanup
        self.page.overlay.append(overlay)
        self.page.update()

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
        result = load_task_file_preview(
            file_path,
            self._option2_selected_task_prefix,
            self._current_preview_limit(),
            (160, 160),
        )
        self._apply_task_preview_result(file_path, result)

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
                    self._build_option2_thumbnail_tile(img_bytes, i)
                )
        else:
            row.alignment = ft.MainAxisAlignment.CENTER
            if self._file_thumbnail_count == 0:
                row.controls.append(
                    ft.Text("画像が見つかりませんでした",
                            size=11, color=ft.Colors.GREY_400, italic=True)
                )

        if info:
            shown = len(self._file_thumbnails)
            meta = self._format_option2_meta_summary()
            if self._file_thumbnail_count > 0:
                info.value = (
                    f"{self._file_thumbnail_count}枚検出 / 表示{shown}枚"
                    f" · クリックで拡大（ズーム/全画面可）"
                )
                if meta:
                    info.value += f" · {meta}"
            else:
                info.value = "画像プレビュー"

    def _pick_option3_folder(self, e):
        async def _run():
            folder = await asyncio.to_thread(select_folder_dialog)
            if folder and self.option3_folder_field.current:
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
        self._option2_all_bmp_paths = []
        self._option2_task_metadata = None
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
                    content_padding=ft.Padding.only(
                        left=10, right=10, top=6, bottom=6),
                ),
                ft.Container(width=93),
            ]),
            ft.Row([
                ft.Text("タスク番号:", width=100, size=14),
                ft.TextField(
                    ref=self.task_num_field, expand=True, hint_text="例: 1",
                    border_radius=6, text_size=13,
                    content_padding=ft.Padding.only(
                        left=10, right=10, top=6, bottom=6),
                ),
                ft.Container(width=93),
            ]),
        ]

    _BROWSE_BUTTON_WIDTH = 96

    def _build_browse_row(
        self,
        field_ref: ft.Ref[ft.TextField],
        hint_text: str,
        on_click,
    ) -> ft.Row:
        """フォルダ／ファイル選択行（参照ボタン幅を揃えテキスト欄の横幅を一致させる）。"""
        return ft.Row(
            [
                ft.TextField(
                    ref=field_ref,
                    expand=True,
                    hint_text=hint_text,
                    border_radius=8,
                    text_size=13,
                    content_padding=ft.Padding.only(
                        left=10, right=10, top=4, bottom=8
                    ),
                ),
                ft.ElevatedButton(
                    "参照",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=on_click,
                    width=self._BROWSE_BUTTON_WIDTH,
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=8)
                    ),
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_preview_limit_row(self) -> list[ft.Control]:
        """表示上限ラベル＋コンパクトな選択ボックス（高さ・縦位置を揃える）。"""
        limit_box = ft.Container(
            width=PREVIEW_LIMIT_BOX_WIDTH,
            height=PREVIEW_LIMIT_ROW_HEIGHT,
            border=ft.Border.all(1, ft.Colors.GREY_400),
            border_radius=4,
            bgcolor=ft.Colors.WHITE,
            padding=ft.Padding.symmetric(horizontal=8),
            content=ft.Row(
                [
                    ft.Text(
                        ref=self.preview_limit_value_text,
                        value=self._preview_limit_value,
                        size=PREVIEW_LIMIT_TEXT_SIZE,
                        color=ft.Colors.GREY_900,
                    ),
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18, color=ft.Colors.GREY_700),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        return [
            ft.Container(
                height=PREVIEW_LIMIT_ROW_HEIGHT,
                content=ft.Row(
                    [
                        ft.Text(
                            "表示上限",
                            size=PREVIEW_LIMIT_TEXT_SIZE,
                            color=ft.Colors.GREY_700,
                        ),
                        ft.PopupMenuButton(
                            ref=self.preview_limit_menu,
                            content=limit_box,
                            items=self._preview_limit_menu_items(),
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            ft.Container(height=PREVIEW_LIMIT_ROW_BOTTOM_GAP),
        ]

    def _build_option2_thumbnail_tile(self, img_bytes: bytes, index: int):
        """プレビュー用サムネイル1枚分の UI。"""
        thumb_px = 112
        label = ""
        if index < len(self._preview_bmp_names):
            label = os.path.basename(self._preview_bmp_names[index])
        return ft.Container(
            width=thumb_px + 8,
            content=ft.Column([
                ft.Container(
                    content=ft.Image(
                        src=img_bytes,
                        width=thumb_px,
                        height=thumb_px,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    border=ft.Border.all(1, ft.Colors.GREY_300),
                    border_radius=4,
                    padding=2,
                    bgcolor=ft.Colors.WHITE,
                    on_click=lambda e, idx=index: self._show_enlarged_image(idx),
                    ink=True,
                ),
                ft.Text(
                    label,
                    size=9,
                    color=ft.Colors.GREY_700,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=1,
                    text_align=ft.TextAlign.CENTER,
                ),
            ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        )

    def _build_option2_fields(self):
        thumbnail_controls = []
        if self._file_thumbnails:
            for i, img_bytes in enumerate(self._file_thumbnails):
                thumbnail_controls.append(
                    self._build_option2_thumbnail_tile(img_bytes, i)
                )
        else:
            thumbnail_controls.append(
                ft.Text(
                    "ファイルを選択するとプレビューが表示されます",
                    size=11,
                    color=ft.Colors.GREY_400,
                    italic=True,
                )
            )

        info_text = "画像プレビュー"
        if self._file_thumbnail_count > 0:
            shown = len(self._file_thumbnails)
            info_text = (
                f"{self._file_thumbnail_count}枚検出 / 表示{shown}枚"
                f" · クリックで拡大（ズーム/全画面可）"
            )
            meta = self._format_option2_meta_summary()
            if meta:
                info_text += f" · {meta}"

        panel_border = ft.Border.all(1, ft.Colors.GREY_200)
        panel_radius = 6

        return [
            self._build_browse_row(
                self.file_path,
                "タスクファイル (.ziq 等)",
                self._pick_file,
            ),
            ft.Container(
                ref=self.option2_workspace,
                expand=True,
                padding=ft.Padding.only(top=4),
                content=ft.Row(
                    [
                        ft.Container(
                            width=300,
                            expand=2,
                            padding=8,
                            border=panel_border,
                            border_radius=panel_radius,
                            bgcolor=ft.Colors.GREY_50,
                            content=ft.Column([
                                ft.Text(
                                    "保存対象タスク（行クリックでプレビュー切替）",
                                    size=11,
                                    weight=ft.FontWeight.W_500,
                                ),
                                *self._build_preview_limit_row(),
                                ft.RadioGroup(
                                    ref=self.option2_save_mode_radio,
                                    value="all",
                                    on_change=self._on_option2_save_mode_changed,
                                    content=ft.Row([
                                        ft.Radio(
                                            value="all",
                                            label="全タスク",
                                        ),
                                        ft.Radio(
                                            value="selected",
                                            label="選択のみ",
                                        ),
                                    ], spacing=0),
                                ),
                                ft.Row([
                                    ft.TextButton(
                                        "全選択",
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.all(4)),
                                        on_click=lambda e:
                                            self._set_option2_group_task_checked(True)),
                                    ft.TextButton(
                                        "全解除",
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.all(4)),
                                        on_click=lambda e:
                                            self._set_option2_group_task_checked(False)),
                                    ft.Text(
                                        ref=self.option2_save_selection_info,
                                        value="",
                                        size=10,
                                        color=ft.Colors.GREY_700,
                                        expand=True,
                                    ),
                                ], spacing=0),
                                ft.Container(
                                    expand=True,
                                    content=ft.Column(
                                        ref=self.option2_task_selection_column,
                                        controls=[
                                            ft.Text(
                                                "タスクファイルを選択してください。",
                                                size=11,
                                                color=ft.Colors.GREY_500,
                                            )
                                        ],
                                        spacing=2,
                                        scroll=ft.ScrollMode.AUTO,
                                    ),
                                ),
                            ], spacing=6, expand=True),
                        ),
                        ft.Container(
                            expand=3,
                            padding=8,
                            border=panel_border,
                            border_radius=panel_radius,
                            bgcolor=ft.Colors.GREY_50,
                            content=ft.Column([
                                ft.Text(
                                    ref=self.thumbnail_info,
                                    value=info_text,
                                    size=11,
                                    color=ft.Colors.GREY_700,
                                ),
                                ft.Container(
                                    expand=True,
                                    content=ft.Column(
                                        scroll=ft.ScrollMode.AUTO,
                                        controls=[
                                            ft.Row(
                                                ref=self.thumbnail_row,
                                                controls=thumbnail_controls,
                                                spacing=6,
                                                wrap=True,
                                                run_spacing=6,
                                                alignment=(
                                                    ft.MainAxisAlignment.CENTER
                                                    if not self._file_thumbnails
                                                    else ft.MainAxisAlignment.START
                                                ),
                                            ),
                                        ],
                                    ),
                                ),
                            ], spacing=4, expand=True),
                        ),
                    ],
                    expand=True,
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
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
                    content_padding=ft.Padding.only(
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

    @staticmethod
    def _parse_int_from_textfield(tf: ft.TextField, default_value: int):
        if tf is None:
            return default_value
        value, error = parse_int_value(tf.value or "", default_value)
        tf.error_text = error
        return value

    def _template_preview_samples(self) -> TemplatePreviewSamples:
        cam, _ = parse_int_value(
            (self.preview_cam_ref.current.value
             if self.preview_cam_ref.current else ""),
            1,
        )
        div, _ = parse_int_value(
            (self.preview_div_ref.current.value
             if self.preview_div_ref.current else ""),
            2,
        )
        index, _ = parse_int_value(
            (self.preview_index_ref.current.value
             if self.preview_index_ref.current else ""),
            3,
        )
        return TemplatePreviewSamples(
            comment=(
                (self.preview_comment_ref.current.value
                 if self.preview_comment_ref.current else "ng") or "ng"
            ),
            tool_capture=(
                (self.preview_tool_capture_ref.current.value
                 if self.preview_tool_capture_ref.current else "画像取込01")
                or "画像取込01"
            ),
            tool_other=(
                (self.preview_tool_other_ref.current.value
                 if self.preview_tool_other_ref.current else "ToolA") or "ToolA"
            ),
            original=(
                (self.preview_original_ref.current.value
                 if self.preview_original_ref.current
                 else "260120115606036_1_1") or "260120115606036_1_1"
            ),
            cam=cam,
            div=div,
            index=index,
            file=(
                (self.preview_file_ref.current.value
                 if self.preview_file_ref.current
                 else "260120115606036") or "260120115606036"
            ),
        )

    def _build_preview(self, template: str, condition: int):
        """テンプレートのプレビュー文字列を生成（condition: 1/2/3）"""
        return build_template_preview(
            template, condition, self._template_preview_samples(),
        )

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
            unknown = extract_unknown_placeholders(template)
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
                            content_padding=ft.Padding.symmetric(
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
                            content_padding=ft.Padding.symmetric(
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
                            content_padding=ft.Padding.symmetric(
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
                                        content_padding=ft.Padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                    ft.TextField(
                                        ref=self.preview_original_ref,
                                        label="original",
                                        value=preview_original_default,
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.Padding.symmetric(
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
                                        content_padding=ft.Padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                    ft.TextField(
                                        ref=self.preview_tool_other_ref,
                                        label="tool(その他)", value="ToolA",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.Padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                ], spacing=8),
                                ft.Row([
                                    ft.TextField(
                                        ref=self.preview_cam_ref,
                                        label="cam", value="1",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.Padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                    ft.TextField(
                                        ref=self.preview_div_ref,
                                        label="div", value="2",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.Padding.symmetric(
                                            horizontal=10, vertical=8),
                                        on_change=on_change,
                                    ),
                                    ft.TextField(
                                        ref=self.preview_index_ref,
                                        label="index", value="3",
                                        dense=True, text_size=11, expand=True,
                                        content_padding=ft.Padding.symmetric(
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
                                        content_padding=ft.Padding.symmetric(
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
            filename_templates = dict(DEFAULT_FILENAME_TEMPLATES)

        def run_processing():
            print(f"処理スレッド開始: {len(task_save_jobs)}タスク, "
                  f"output={output_folder}")
            run_image_processing_jobs(
                task_save_jobs,
                img_folder_path,
                output_folder,
                save_mode,
                save_cam,
                compression,
                selected_cam_list,
                filename_templates,
                ps,
                self._update_progress,
                cleanup_paths,
            )

        # 状態を初期化
        ps.update({
            'is_processing': True, 'current': 0, 'total': 0,
            'message': '準備中...', 'completed': False, 'error': None,
            'cancelled': False, 'created_files': [],
            'output_folder': output_folder,
        })

        ps['existing_files'] = snapshot_output_files(output_folder)

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

            img_folder_path = build_option1_img_path(group_num, task_num)

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

            img_folder_path = build_option3_img_path(
                option3_folder, group_num, task_num,
            )

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
            result = prepare_option2_extraction(
                task_file,
                output_folder,
                self._option2_task_folders,
                self._last_option2_loaded_file,
                selected_task_prefix,
                save_target_mode,
                selected_save_prefixes,
            )
            loading_result.update(result)

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
        sidebar_controls = [
            ft.Text("タスク画像保存フロー", size=18, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text(
                ref=self.info_text,
                value=OPTION_DESCRIPTIONS["option1"],
                size=14,
            ),
        ]
        if is_file_dropzone_available():
            sidebar_controls.extend([
                ft.Divider(height=1),
                ft.Text(
                    "タスクファイル (.ziq 等) を\nウィンドウへドラッグ＆ドロップ",
                    size=11,
                    color=ft.Colors.BLUE_900,
                ),
            ])
            if not should_use_file_dropzone():
                hint = dropzone_setup_hint()
                if hint:
                    sidebar_controls.append(
                        ft.Text(f"※ {hint}", size=10, color=ft.Colors.GREY_600),
                    )
        return ft.Container(
            width=220,
            bgcolor=ft.Colors.GREY_100,
            padding=15,
            alignment=ft.Alignment(-1, -1),
            content=ft.Column(
                sidebar_controls,
                scroll=ft.ScrollMode.AUTO,
                alignment=ft.MainAxisAlignment.START,
            ),
        )

    def _build_main_content(self):
        return ft.Container(
            expand=True,
            padding=ft.Padding.only(left=20, right=20, top=15, bottom=15),
            alignment=ft.Alignment(-1, -1),
            content=ft.Column([
                ##ft.Text("タスク画像保存フロー",
                ##        size=20, weight=ft.FontWeight.BOLD),
                ##ft.Container(
                #    height=2, bgcolor=ft.Colors.BLUE, border_radius=2),
                ##ft.Container(height=10),

                ft.Container(
                    ref=self.import_source_section,
                    visible=True,
                    content=ft.Column([
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
                    ], spacing=4),
                ),
                ft.Container(height=8),

                ft.Text("画像を保存するフォルダを選択",
                        size=15, weight=ft.FontWeight.W_500),
                self._build_browse_row(
                    self.folder_path,
                    "フォルダを選択...",
                    self._pick_folder,
                ),

                ft.Text(ref=self.warning_text, value="",
                        color=ft.Colors.RED, size=11),
                ft.Container(height=5),

                ft.Container(
                    expand=True,
                    content=ft.Column(
                        ref=self.dynamic_content,
                        spacing=6,
                        expand=True,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ),

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
            expand=True,
            alignment=ft.MainAxisAlignment.START,
            ),
        )

    def _build_ui(self):
        root = ft.Row(
            [
                self._build_sidebar(),
                ft.VerticalDivider(width=1),
                self._build_main_content(),
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        if should_use_file_dropzone():
            root = wrap_with_task_file_dropzone(
                root,
                self._handle_dropped_task_file,
                self.page,
            )
        self.page.add(root)
        self.page.update()
