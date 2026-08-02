"""
Flet によるタスク画像保存アプリの UI 層。
ビジネスロジックは task_image_saver_logic、リソースは flet_resources を参照する。
"""
import asyncio
from collections import defaultdict
import math
import os
import re
import threading
from datetime import datetime
from typing import Literal

import flet as ft
import flet.canvas as cv
import save_task_images_CamNum_selection
from config import ConfigManager, Constants
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
    THUMBNAIL_UI_UPDATE_BATCH,
    LOAD_TASK_LIST_BUTTON_LABEL,
    LOCAL_TASK_LIST_PLACEHOLDER,
    LOCAL_TASK_LIST_LOADING,
    SIDEBAR_COLLAPSED_STORAGE_KEY,
    SIDEBAR_WIDTH_COLLAPSED,
    SIDEBAR_WIDTH_EXPANDED,
    VIEWER_FOOTER_HEIGHT,
    DEFAULT_VIEWER_GRID_SPACING,
    VIEWER_GRID_SPACING_OPTIONS,
    VIEWER_GRID_ZOOM_THRESHOLD,
    VIEWER_HEADER_HEIGHT,
    VIEWER_MAX_SCALE,
    VIEWER_MIN_SCALE,
    VIEWER_PANEL_HEIGHT,
    VIEWER_PANEL_PADDING,
    VIEWER_PANEL_WIDTH,
)
from task_image_saver_logic import (
    TemplatePreviewSamples,
    build_option1_img_path,
    build_option3_img_path,
    build_template_preview,
    extract_unknown_placeholders,
    extract_viewer_bmp_from_path,
    extract_viewer_bmp_from_zip,
    filter_save_task_folders,
    find_task_folder_by_prefix,
    load_folder_preview,
    load_task_file_preview,
    parse_int_value,
    prepare_option2_extraction,
    run_image_processing_jobs,
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
    list_filesystem_task_folders,
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
        self._local_task_folders: list[TaskFolder] = []
        self._local_selected_task_prefix: str | None = None
        self._preview_source: Literal["zip", "folder"] = "zip"
        self._preview_img_folder = ""
        self._local_task_list_loading = False
        self._local_preview_generation = 0
        self._launch_task_file = (
            launch_task_file if launch_task_file and is_task_file_path(launch_task_file)
            else None
        )
        self._sidebar_expanded = True

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
        self.option2_select_all_btn = ft.Ref[ft.TextButton]()
        self.option2_deselect_all_btn = ft.Ref[ft.TextButton]()
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
        self.local_task_selection_column = ft.Ref[ft.Column]()
        self.local_task_workspace = ft.Ref[ft.Container]()
        self.load_task_list_btn = ft.Ref[ft.ElevatedButton]()
        self.import_source_section = ft.Ref[ft.Container]()
        self.sidebar_container = ft.Ref[ft.Container]()
        self.sidebar_content = ft.Ref[ft.Container]()
        self.sidebar_toggle = ft.Ref[ft.IconButton]()

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
        self._load_sidebar_state()

    def _load_sidebar_state(self) -> None:
        """前回セッションのサイドバー折りたたみ状態を復元する。"""
        try:
            collapsed = self.page.client_storage.get(SIDEBAR_COLLAPSED_STORAGE_KEY)
            if collapsed is not None:
                self._sidebar_expanded = not bool(collapsed)
        except Exception:
            pass

    def _save_sidebar_state(self) -> None:
        try:
            self.page.client_storage.set(
                SIDEBAR_COLLAPSED_STORAGE_KEY,
                not self._sidebar_expanded,
            )
        except Exception:
            pass

    def _toggle_sidebar(self, _e) -> None:
        self._sidebar_expanded = not self._sidebar_expanded
        self._apply_sidebar_state()
        self._save_sidebar_state()

    def _apply_sidebar_state(self) -> None:
        expanded = self._sidebar_expanded
        sidebar = self.sidebar_container.current
        content = self.sidebar_content.current
        toggle = self.sidebar_toggle.current
        if sidebar is not None:
            sidebar.width = SIDEBAR_WIDTH_EXPANDED if expanded else SIDEBAR_WIDTH_COLLAPSED
            sidebar.padding = (
                ft.Padding(left=15, right=15, top=15, bottom=15)
                if expanded
                else ft.Padding(left=0, right=0, top=8, bottom=8)
            )
        if content is not None:
            content.visible = expanded
        if toggle is not None:
            toggle.icon = ft.Icons.CHEVRON_LEFT if expanded else ft.Icons.CHEVRON_RIGHT
            toggle.tooltip = (
                "サイドバーを折りたたむ" if expanded else "サイドバーを表示"
            )
        self.page.update()

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
        row = self.thumbnail_row.current
        if row:
            row.update()

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

    def _current_option(self) -> str:
        return (
            self.selected_option.current.value
            if self.selected_option.current else "option1"
        )

    def _local_task_list_task_root(self, option: str | None = None) -> str | None:
        option = option or self._current_option()
        if option == "option1":
            return Constants.DEFAULT_VISCO_TECH_PATH
        if option == "option3":
            folder = (
                self.option3_folder_field.current.value
                if self.option3_folder_field.current else ""
            )
            if not folder:
                return None
            return os.path.join(folder, "task")
        return None

    def _is_load_task_list_enabled(self) -> bool:
        if self._local_task_list_loading:
            return False
        if self._current_option() == "option3":
            return bool(self._local_task_list_task_root("option3"))
        return True

    def _update_load_task_list_button(self) -> None:
        btn = self.load_task_list_btn.current
        if btn is None:
            return
        btn.disabled = not self._is_load_task_list_enabled()
        btn.content = (
            LOCAL_TASK_LIST_LOADING
            if self._local_task_list_loading
            else LOAD_TASK_LIST_BUTTON_LABEL
        )

    def _on_load_task_list_click(self, _e):
        self.page.run_task(self._load_local_task_list_async)

    async def _load_local_task_list_async(self):
        option = self._current_option()
        task_root = self._local_task_list_task_root(option)
        if not task_root:
            if self.warning_text.current:
                self.warning_text.current.value = (
                    "外部のviscotechフォルダを選択してください"
                    if option == "option3"
                    else "タスクフォルダが見つかりません"
                )
            self.page.update()
            return

        self._local_task_list_loading = True
        if self.warning_text.current:
            self.warning_text.current.value = ""
        self._update_load_task_list_button()
        self.page.update()

        try:
            folders = await asyncio.to_thread(
                list_filesystem_task_folders, task_root,
            )
        except Exception as exc:
            if self.warning_text.current:
                self.warning_text.current.value = (
                    f"タスク一覧の読み込みエラー: {exc}"
                )
            folders = []
        finally:
            self._local_task_list_loading = False
            self._update_load_task_list_button()

        self._local_task_folders = folders
        self._local_selected_task_prefix = (
            folders[0].prefix if folders else None
        )
        self._update_local_task_list_controls()
        if self.preview_limit_menu.current:
            self.preview_limit_menu.current.disabled = False
        self.page.update()

        if folders and self._local_selected_task_prefix:
            await self._load_local_task_preview(self._local_selected_task_prefix)

    def _sync_group_task_fields_from_folder(self, folder: TaskFolder) -> None:
        group = task_folder_group(folder)
        task = task_folder_task(folder)
        group_num = re.sub(r"^g", "", group, flags=re.IGNORECASE)
        if self.group_num_field.current:
            try:
                self.group_num_field.current.value = str(int(group_num))
            except ValueError:
                self.group_num_field.current.value = group_num
        if self.task_num_field.current:
            try:
                self.task_num_field.current.value = str(int(task))
            except ValueError:
                self.task_num_field.current.value = task

    def _update_local_task_list_controls(self):
        selection_column = self.local_task_selection_column.current
        if not selection_column:
            return

        selection_column.controls.clear()
        folders = self._local_task_folders
        if not folders:
            selection_column.controls.append(
                ft.Text(
                    LOCAL_TASK_LIST_PLACEHOLDER,
                    size=11,
                    color=ft.Colors.GREY_500,
                )
            )
            selection_column.update()
            return

        current_prefix = self._local_selected_task_prefix
        for folder in folders:
            is_current = folder.prefix == current_prefix
            group = task_folder_group(folder)
            task = task_folder_task(folder)
            title = folder.title or "タイトルなし"
            comment = folder.comment or ""
            has_images = folder.image_count > 0
            image_status = (
                f"画像 {folder.image_count}枚" if has_images else "画像なし"
            )
            image_status_color = (
                ft.Colors.GREEN_700 if has_images else ft.Colors.RED_700
            )
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
                        self._select_local_task_folder(task_folder),
                    content=ft.Row([
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

        selection_column.update()

    def _select_local_task_folder(self, folder: TaskFolder):
        self.page.run_task(self._load_local_task_preview, folder.prefix)

    async def _load_local_task_preview(self, task_prefix: str):
        selected = find_task_folder_by_prefix(
            self._local_task_folders, task_prefix,
        )
        if not selected:
            return

        self._local_preview_generation += 1
        generation = self._local_preview_generation
        self._local_selected_task_prefix = selected.prefix
        self._sync_group_task_fields_from_folder(selected)
        self._update_local_task_list_controls()
        self._show_thumbnail_loading()
        row = self.thumbnail_row.current
        if row:
            row.update()

        img_folder = os.path.join(selected.prefix, "img")
        max_images = self._current_preview_limit()
        result = await asyncio.to_thread(
            load_folder_preview,
            img_folder,
            selected.prefix,
            max_images,
            (160, 160),
        )
        if generation != self._local_preview_generation:
            return

        self._apply_task_preview_result(
            result,
            preview_source="folder",
            source_path=img_folder,
        )
        self._enrich_task_folder_from_metadata(selected, result.metadata)
        self._update_local_task_list_controls()
        await self._update_thumbnail_display_async()

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
        self.page.run_task(self._reload_current_preview)

    async def _reload_current_preview(self):
        option = (
            self.selected_option.current.value
            if self.selected_option.current else "option1"
        )
        if option == "option2":
            await self._reload_option2_preview()
        elif (
            option in ("option1", "option3")
            and self._local_selected_task_prefix
        ):
            await self._load_local_task_preview(self._local_selected_task_prefix)

    def _apply_task_preview_result(
        self,
        result,
        *,
        preview_source: Literal["zip", "folder"],
        source_path: str = "",
    ) -> None:
        self._file_thumbnails = result.thumbnail_bytes
        self._file_thumbnail_count = result.total_bmp_count
        self._preview_bmp_names = result.thumbnail_paths
        self._option2_all_bmp_paths = result.all_bmp_paths
        self._option2_task_metadata = result.metadata
        self._preview_source = preview_source
        if preview_source == "zip":
            self._preview_zip_path = source_path
            self._preview_img_folder = ""
        else:
            self._preview_zip_path = ""
            self._preview_img_folder = source_path

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

    def _enrich_task_folder_from_metadata(
        self,
        folder: TaskFolder,
        metadata,
    ) -> None:
        if not metadata:
            return
        if metadata.title:
            folder.title = metadata.title
        if metadata.comment:
            folder.comment = metadata.comment
        if metadata.last_updated:
            folder.updated_at = metadata.last_updated

    def _folder_meta_line(self, folder: TaskFolder, is_current: bool) -> str:
        """リスト行用のメタ情報（Ver・更新日など）。"""
        parts: list[str] = []
        if is_current:
            summary = self._format_option2_meta_summary()
            if summary:
                return summary
        if folder.updated_at:
            parts.append(f"更新 {folder.updated_at}")
        return " · ".join(parts)

    def _thumbnail_info_text(self) -> str:
        shown = len(self._file_thumbnails)
        meta = self._format_option2_meta_summary()
        if self._file_thumbnail_count > 0:
            text = (
                f"{self._file_thumbnail_count}枚検出 / 表示{shown}枚"
                f" · クリックで拡大（ズーム/全画面可）"
            )
            if meta:
                text += f" · {meta}"
            return text
        return "画像プレビュー"

    async def _update_thumbnail_display_async(self) -> None:
        """サムネイル行を分割更新し UI スレッドの固まりを防ぐ。"""
        row = self.thumbnail_row.current
        info = self.thumbnail_info.current
        if not row:
            return

        row.controls.clear()
        thumbs = self._file_thumbnails
        if thumbs:
            row.alignment = ft.MainAxisAlignment.START
            batch_size = THUMBNAIL_UI_UPDATE_BATCH
            for i, img_bytes in enumerate(thumbs):
                row.controls.append(
                    self._build_thumbnail_tile(img_bytes, i)
                )
                if (i + 1) % batch_size == 0:
                    if info:
                        info.value = self._thumbnail_info_text()
                    await asyncio.sleep(0)
                    if info:
                        row.update()
                        info.update()
                    else:
                        row.update()
        else:
            row.alignment = ft.MainAxisAlignment.CENTER
            if self._file_thumbnail_count == 0:
                row.controls.append(
                    ft.Text(
                        "画像が見つかりませんでした",
                        size=11,
                        color=ft.Colors.GREY_400,
                        italic=True,
                    )
                )

        if info:
            info.value = self._thumbnail_info_text()
        await asyncio.sleep(0)
        if info:
            row.update()
            info.update()
        else:
            row.update()

    async def _load_option2_preview_async(self, file_path: str) -> None:
        max_images = self._current_preview_limit()
        result = await asyncio.to_thread(
            load_task_file_preview,
            file_path,
            self._option2_selected_task_prefix,
            max_images,
            (160, 160),
        )
        self._apply_task_preview_result(
            result,
            preview_source="zip",
            source_path=file_path,
        )
        await self._update_thumbnail_display_async()

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
        row = self.thumbnail_row.current
        if row:
            row.update()
        await self._load_option2_preview_async(file_path)

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
        save_mode = self._option2_save_mode()
        selection_enabled = save_mode == "selected"
        select_all_btn = self.option2_select_all_btn.current
        deselect_all_btn = self.option2_deselect_all_btn.current
        if select_all_btn is not None:
            select_all_btn.disabled = not selection_enabled
        if deselect_all_btn is not None:
            deselect_all_btn.disabled = not selection_enabled

        if not folders:
            selection_column.controls.append(
                ft.Text("タスクファイルを選択してください。",
                        size=11, color=ft.Colors.GREY_500)
            )
            if info_control:
                info_control.value = ""
            return

        if len(folders) > 1 and not selection_enabled:
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
            total_count = len(folders)
            if selection_enabled:
                selected_count = len(self._option2_save_task_prefixes)
                info_control.value = (
                    f"保存対象: {selected_count} / {total_count} タスク")
            else:
                info_control.value = f"保存対象: 全 {total_count} タスク"

        selection_column.update()

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
        if self._option2_save_mode() != "selected":
            return
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
        row = self.thumbnail_row.current
        if row:
            row.update()

        file_path = self.file_path.current.value if self.file_path.current else ""
        await self._load_option2_preview_async(file_path)

    def _viewer_bmp_paths(self) -> list[str]:
        return self._option2_all_bmp_paths or self._preview_bmp_names

    @staticmethod
    def _remove_temp_file(path: str | None) -> None:
        if not path:
            return
        try:
            os.remove(path)
        except OSError:
            pass

    def _close_image_viewer(self):
        """表示中の画像プレビューオーバーレイを閉じる。"""
        cleanup = self._image_viewer_cleanup
        self._image_viewer_cleanup = None
        if cleanup:
            cleanup()

    def _show_enlarged_image(self, thumb_index: int):
        """サムネイルクリック時に拡大画像を表示する"""
        if not self._preview_bmp_names:
            return
        if self._preview_source == "zip" and not self._preview_zip_path:
            return
        if self._preview_source == "folder" and not self._preview_img_folder:
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
        if not bmp_paths:
            return
        if self._preview_source == "zip" and not self._preview_zip_path:
            return
        if self._preview_source == "folder" and not self._preview_img_folder:
            return

        self._close_image_viewer()

        state = {
            "idx": start_index,
            "bmp_tmp": None,
            "width": 0,
            "height": 0,
            "fullscreen": False,
            "prev_window_full_screen": bool(self.page.window.full_screen),
            "viewer_scale": 1.0,
            "tx": 0.0,
            "ty": 0.0,
            "gesture_start_scale": 1.0,
            "gesture_ref_scene": None,
            "gesture_prev_focal": None,
            "gesture_was_pan": False,
            "fit_scale": 1.0,
            "grid_enabled": True,
            "grid_spacing": DEFAULT_VIEWER_GRID_SPACING,
            "grid_visible": False,
            "grid_drawn": None,
            "grid_rebuild_busy": False,
            "load_generation": 0,
        }
        overlay_ref = ft.Ref[ft.Container]()
        panel_ref = ft.Ref[ft.Container]()
        viewer_area_ref = ft.Ref[ft.Container]()
        viewer_ref = ft.Ref[ft.InteractiveViewer]()
        stack_ref = ft.Ref[ft.Stack]()
        img_ref = ft.Ref[ft.Image]()
        grid_canvas_ref = ft.Ref[cv.Canvas]()
        loading_ref = ft.Ref[ft.Container]()
        counter_ref = ft.Ref[ft.Text]()
        name_ref = ft.Ref[ft.Text]()
        fullscreen_btn_ref = ft.Ref[ft.IconButton]()
        grid_toggle_btn_ref = ft.Ref[ft.IconButton]()
        grid_spacing_text_ref = ft.Ref[ft.Text]()
        header_ref = ft.Ref[ft.Row]()
        footer_ref = ft.Ref[ft.Container]()


        def cleanup_viewer_temps() -> None:
            self._remove_temp_file(state.get("bmp_tmp"))
            state["bmp_tmp"] = None

        def viewer_area_size() -> tuple[float, float]:
            """画像表示領域（InteractiveViewer）の論理サイズを返す。"""
            if state["fullscreen"]:
                width = float(self.page.width or VIEWER_PANEL_WIDTH)
                height = (
                    float(self.page.height or VIEWER_PANEL_HEIGHT)
                    - VIEWER_FOOTER_HEIGHT
                )
            else:
                width = VIEWER_PANEL_WIDTH - 2 * VIEWER_PANEL_PADDING
                height = (
                    VIEWER_PANEL_HEIGHT
                    - 2 * VIEWER_PANEL_PADDING
                    - VIEWER_HEADER_HEIGHT
                    - VIEWER_FOOTER_HEIGHT
                )
            return max(width, 1.0), max(height, 1.0)

        # グリッドは Canvas で可視範囲＋余白のみ描画する（透過PNG重ねは
        # Flet クライアントで全面グレーになるため使用しない）。
        # Path は丸ごと差し替え、要素生成はワーカースレッドで行う。
        GRID_LINE_BUDGET = 1200.0
        GRID_VIEW_MARGIN = 0.5

        # パン終了時の慣性摩擦係数。Flutter の FrictionSimulation は速度が
        # drag^t で減衰するため「小さいほど即停止」する（0.01 のような値は
        # 逆にデフォルトより慣性が伸びる）。慣性アニメーション中は update
        # イベントが届かず変換追跡がずれるので、実質ゼロまで小さくする
        # （最大移動量 = 速度 / |ln(drag)| ≒ 速度/690 ≦ 数px）。
        FLING_FRICTION = 1e-300
        FLING_LOG = abs(math.log(FLING_FRICTION))

        def grid_show_threshold() -> float:
            """グリッド表示を開始する倍率（間隔が広いほど低倍率で表示）。"""
            spacing = max(1, int(state["grid_spacing"]))
            return float(VIEWER_GRID_ZOOM_THRESHOLD) / spacing

        def grid_hide_threshold() -> float:
            """グリッドを隠す倍率（ヒステリシスで境界付近のチラつきを防ぐ）。"""
            return grid_show_threshold() * 0.85

        def grid_should_show(scale: float) -> bool:
            if not state["grid_enabled"] or state["width"] <= 0:
                return False
            if scale >= grid_show_threshold():
                return True
            if scale < grid_hide_threshold():
                return False
            return state["grid_visible"]

        def visible_content_rect() -> tuple[float, float, float, float]:
            """表示領域に映っているコンテンツ座標範囲を返す。"""
            scale = max(state["viewer_scale"], 1e-6)
            area_w, area_h = viewer_area_size()
            x0 = (0 - state["tx"]) / scale
            y0 = (0 - state["ty"]) / scale
            return x0, y0, x0 + area_w / scale, y0 + area_h / scale

        def _grid_region() -> tuple[int, int, int, int] | None:
            width, height = state["width"], state["height"]
            if width <= 0 or height <= 0:
                return None
            x0, y0, x1, y1 = visible_content_rect()
            step = max(1, int(state["grid_spacing"]))
            vis_lines = (x1 - x0) / step + (y1 - y0) / step
            margin = min(
                GRID_VIEW_MARGIN,
                max(
                    0.0,
                    (GRID_LINE_BUDGET - vis_lines)
                    / max(2 * vis_lines, 1e-6),
                ),
            )
            mx = (x1 - x0) * margin
            my = (y1 - y0) * margin
            gx0 = max(0, math.floor(x0 - mx))
            gx1 = min(width, math.ceil(x1 + mx))
            gy0 = max(0, math.floor(y0 - my))
            gy1 = min(height, math.ceil(y1 + my))
            if gx1 <= gx0 or gy1 <= gy0:
                return None
            return gx0, gy0, gx1, gy1

        def _grid_elements_for_region(
            gx0: int, gy0: int, gx1: int, gy1: int,
            width: int, height: int,
            step: int = 1,
        ) -> list[cv.Path.PathElement]:
            step = max(1, int(step))
            elements: list[cv.Path.PathElement] = []
            x_lo = max(1, gx0)
            x_hi = min(width - 1, gx1)
            x_start = ((x_lo + step - 1) // step) * step
            for x in range(x_start, x_hi + 1, step):
                elements.append(cv.Path.MoveTo(x, gy0))
                elements.append(cv.Path.LineTo(x, gy1))
            y_lo = max(1, gy0)
            y_hi = min(height - 1, gy1)
            y_start = ((y_lo + step - 1) // step) * step
            for y in range(y_start, y_hi + 1, step):
                elements.append(cv.Path.MoveTo(gx0, y))
                elements.append(cv.Path.LineTo(gx1, y))
            return elements

        def _viewer_is_active() -> bool:
            return self._image_viewer_cleanup is not None

        def clear_grid_cache():
            """画像切替時にグリッドの描画キャッシュを破棄する。"""
            canvas = grid_canvas_ref.current
            state["grid_drawn"] = None
            state["grid_rebuild_busy"] = False
            state["grid_visible"] = False
            if canvas:
                canvas.shapes = []
                canvas.visible = False

        def hide_grid_now():
            """グリッドを隠す。"""
            if not _viewer_is_active():
                return
            canvas = grid_canvas_ref.current
            if not canvas or not state["grid_visible"]:
                return
            state["grid_visible"] = False
            state["grid_drawn"] = None
            canvas.shapes = []
            canvas.visible = False
            canvas.update()

        async def rebuild_grid_async():
            """可視範囲のグリッドを非同期で再構築する。"""
            if not _viewer_is_active() or state.get("grid_rebuild_busy"):
                return
            scale = max(state["viewer_scale"], 1e-6)
            if not grid_should_show(scale):
                hide_grid_now()
                return

            region = _grid_region()
            if region is None:
                hide_grid_now()
                return
            gx0, gy0, gx1, gy1 = region
            width, height = state["width"], state["height"]
            drawn = state.get("grid_drawn")
            spacing = max(1, int(state["grid_spacing"]))
            if (
                state["grid_visible"]
                and drawn
                and drawn[0] == (gx0, gy0, gx1, gy1)
                and drawn[1] == spacing
                and abs(drawn[2] - scale) / max(scale, 1e-6) < 0.02
            ):
                return

            state["grid_rebuild_busy"] = True
            try:
                elements = await asyncio.to_thread(
                    _grid_elements_for_region,
                    gx0, gy0, gx1, gy1, width, height,
                    spacing,
                )
                await asyncio.sleep(0)
                if not _viewer_is_active() or not grid_should_show(scale):
                    return
                canvas = grid_canvas_ref.current
                if not canvas:
                    return
                canvas.shapes = [
                    cv.Path(
                        elements=elements,
                        paint=ft.Paint(
                            color=ft.Colors.with_opacity(
                                0.6, ft.Colors.BLUE_400,
                            ),
                            stroke_width=min(
                                0.25, max(0.03, 1.0 / scale),
                            ),
                            style=ft.PaintingStyle.STROKE,
                        ),
                    ),
                ]
                state["grid_drawn"] = ((gx0, gy0, gx1, gy1), spacing, scale)
                state["grid_visible"] = True
                canvas.visible = True
                canvas.update()
            finally:
                state["grid_rebuild_busy"] = False

        def sync_grid():
            """しきい値に応じてグリッドを再構築または非表示にする。"""
            if not _viewer_is_active():
                return
            scale = max(state["viewer_scale"], 1e-6)
            if not grid_should_show(scale):
                hide_grid_now()
                return
            self.page.run_task(rebuild_grid_async)

        async def sync_grid_deferred():
            """UIイベント処理後にグリッド表示を同期する。"""
            await asyncio.sleep(0)
            sync_grid()

        # reset/zoom/pan の3呼び出しは非アトミックなため、ボタン連打などで
        # 並行実行されると実際の変換と追跡値がずれる。ロックで直列化する。
        transform_lock = asyncio.Lock()

        async def _set_scale_centered_locked(scale: float):
            viewer = viewer_ref.current
            if not viewer or state["width"] <= 0:
                return
            min_scale = float(viewer.min_scale or VIEWER_MIN_SCALE)
            scale = max(min_scale, min(VIEWER_MAX_SCALE, scale))
            area_w, area_h = viewer_area_size()
            await viewer.reset()
            if abs(scale - 1.0) > 1e-6:
                await viewer.zoom(scale)
            # zoom() は原点基準のため、中央寄せ分を pan で補正する
            # （pan の移動量はコンテンツ座標系 = 倍率適用前の値）
            dx = (area_w - state["width"] * scale) / (2 * scale)
            dy = (area_h - state["height"] * scale) / (2 * scale)
            await viewer.pan(dx, dy)
            state["viewer_scale"] = scale
            # 変換行列を正確に記録（screen = scale * content + t）
            state["tx"] = scale * dx
            state["ty"] = scale * dy
            sync_grid()

        async def set_scale_centered(scale: float):
            """指定倍率で画像中心が表示領域中央に来るよう変換を組み直す。"""
            async with transform_lock:
                await _set_scale_centered_locked(scale)

        async def apply_fit_async(*, wait_layout: bool = False):
            """画像全体が収まる倍率にリセットする。"""
            viewer = viewer_ref.current
            if not viewer or state["width"] <= 0:
                return
            if wait_layout:
                # 全画面切替直後はページサイズ反映を待つ
                await asyncio.sleep(0.25)
            area_w, area_h = viewer_area_size()
            fit = min(
                area_w / state["width"],
                area_h / state["height"],
                1.0,
            )
            fit = max(fit, VIEWER_MIN_SCALE)
            state["fit_scale"] = fit
            viewer.min_scale = max(VIEWER_MIN_SCALE, min(0.5, fit))
            viewer.update()
            await set_scale_centered(fit)

        def reset_zoom(_e=None):
            self.page.run_task(apply_fit_async)

        async def zoom_in(_e):
            # 現在倍率はロック取得後に読む（連打時の取りこぼし防止）
            async with transform_lock:
                await _set_scale_centered_locked(state["viewer_scale"] * 1.5)

        async def zoom_out(_e):
            async with transform_lock:
                await _set_scale_centered_locked(state["viewer_scale"] / 1.5)

        async def zoom_to_original(_e):
            """画像1ピクセル = 画面1ピクセル（等倍）にする。"""
            await set_scale_centered(1.0)

        def zoom_in_click(_e):
            self.page.run_task(zoom_in, _e)

        def zoom_out_click(_e):
            self.page.run_task(zoom_out, _e)

        def zoom_to_original_click(_e):
            self.page.run_task(zoom_to_original, _e)

        def on_interaction_start(e):
            # ジェスチャー開始時の倍率と、焦点直下のコンテンツ座標を記録。
            # ホイールズームは1ティックごとに start/update/end を発生させ、
            # ドラッグ中に割り込むこともある（その場合も基準を取り直す）。
            scale = max(state["viewer_scale"], 1e-6)
            state["gesture_start_scale"] = scale
            state["gesture_ref_scene"] = (
                (e.local_focal_point.x - state["tx"]) / scale,
                (e.local_focal_point.y - state["ty"]) / scale,
            )
            state["gesture_prev_focal"] = (
                e.local_focal_point.x,
                e.local_focal_point.y,
            )
            state["gesture_was_pan"] = False
            hide_grid_now()

        def on_interaction_update(e):
            ref = state.get("gesture_ref_scene")
            prev = state.get("gesture_prev_focal")
            if not ref or not prev:
                return
            fx, fy = e.local_focal_point.x, e.local_focal_point.y
            if abs(e.scale - 1.0) > 1e-9:
                # ズーム系（ホイール / ピンチ）: Flutter と同じ
                # 「焦点直下のコンテンツ点を維持」する変換を再現
                viewer = viewer_ref.current
                min_scale = float(
                    (viewer.min_scale if viewer else None)
                    or VIEWER_MIN_SCALE
                )
                scale = max(
                    min_scale,
                    min(
                        VIEWER_MAX_SCALE,
                        state["gesture_start_scale"] * e.scale,
                    ),
                )
                state["viewer_scale"] = scale
                state["tx"] = fx - scale * ref[0]
                state["ty"] = fy - scale * ref[1]
                # 全体グリッドは変換に追従するため update 中は何もしない。
                # 表示切替は interaction_end で1回だけ行う。
            else:
                # パン系: 焦点の移動量だけ平行移動（Flutter のパン処理と
                # 同じ差分方式）。絶対座標の差分なので、間にホイールが
                # 割り込んでも誤差が蓄積しない
                state["tx"] += fx - prev[0]
                state["ty"] += fy - prev[1]
                state["gesture_was_pan"] = True
            state["gesture_prev_focal"] = (fx, fy)

        def on_interaction_end(e):
            # 基準点は消さない（ドラッグ中にホイールの end が割り込んでも
            # 続きのドラッグ更新を処理できるようにするため）。
            # パン終了時に速度が 50px/s 以上あると Flutter は慣性
            # アニメーションを行うが、その間 update イベントは届かない。
            # 終端位置は FrictionSimulation の解析解
            # （移動量 = 速度 / |ln(摩擦係数)|）で確定するため、
            # ここで先取りして追跡へ反映する。
            if state.get("gesture_was_pan"):
                vx = float(e.velocity.x or 0.0)
                vy = float(e.velocity.y or 0.0)
                if math.hypot(vx, vy) >= 50.0:
                    state["tx"] += vx / FLING_LOG
                    state["ty"] += vy / FLING_LOG
            self.page.run_task(sync_grid_deferred)

        def toggle_grid(_e):
            state["grid_enabled"] = not state["grid_enabled"]
            if grid_toggle_btn_ref.current:
                grid_toggle_btn_ref.current.icon = (
                    ft.Icons.GRID_ON
                    if state["grid_enabled"]
                    else ft.Icons.GRID_OFF
                )
                grid_toggle_btn_ref.current.tooltip = (
                    "ピクセルグリッドを非表示"
                    if state["grid_enabled"]
                    else "ピクセルグリッドを表示"
                )
            if state["grid_enabled"]:
                sync_grid()
            else:
                hide_grid_now()
            self.page.update()

        def set_grid_spacing(spacing: int):
            state["grid_spacing"] = spacing
            state["grid_drawn"] = None
            if grid_spacing_text_ref.current:
                grid_spacing_text_ref.current.value = f"{spacing}px"
            if state["grid_enabled"]:
                sync_grid()
            else:
                hide_grid_now()
            self.page.update()

        def grid_spacing_menu_items() -> list[ft.PopupMenuItem]:
            items: list[ft.PopupMenuItem] = []

            def make_handler(selected: int):
                def handler(_e):
                    set_grid_spacing(selected)
                return handler

            for option in VIEWER_GRID_SPACING_OPTIONS:
                items.append(
                    ft.PopupMenuItem(
                        content=f"{option}px",
                        on_click=make_handler(option),
                    )
                )
            return items

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
                panel_ref.current.width = (
                    None if fullscreen else VIEWER_PANEL_WIDTH
                )
                panel_ref.current.height = (
                    None if fullscreen else VIEWER_PANEL_HEIGHT
                )
                panel_ref.current.bgcolor = (
                    ft.Colors.BLACK if fullscreen else ft.Colors.WHITE
                )
                panel_ref.current.border_radius = 0 if fullscreen else 8
                panel_ref.current.padding = (
                    ft.Padding.all(0)
                    if fullscreen
                    else ft.Padding.all(VIEWER_PANEL_PADDING)
                )
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
            self.page.update()
            self.page.run_task(refit_after_layout)

        async def refit_after_layout():
            await apply_fit_async(wait_layout=True)

        def toggle_fullscreen(_e):
            state["fullscreen"] = not state["fullscreen"]
            apply_layout()

        async def load_current_image_async():
            generation = state["load_generation"]
            idx = state["idx"]
            if idx < 0 or idx >= len(bmp_paths):
                return

            clear_grid_cache()
            if loading_ref.current:
                loading_ref.current.visible = True
            if img_ref.current:
                img_ref.current.visible = False
            self.page.update()

            try:
                if self._preview_source == "zip":
                    asset = await asyncio.to_thread(
                        extract_viewer_bmp_from_zip,
                        self._preview_zip_path,
                        bmp_paths[idx],
                    )
                else:
                    asset = await asyncio.to_thread(
                        extract_viewer_bmp_from_path,
                        bmp_paths[idx],
                    )

                if generation != state["load_generation"]:
                    if asset:
                        self._remove_temp_file(asset.temp_path)
                    return

                if not asset:
                    return

                old_bmp = state.get("bmp_tmp")
                size_changed = (
                    (state["width"], state["height"])
                    != (asset.width, asset.height)
                )
                state["bmp_tmp"] = asset.temp_path
                state["width"] = asset.width
                state["height"] = asset.height

                if stack_ref.current:
                    stack_ref.current.width = asset.width
                    stack_ref.current.height = asset.height
                if img_ref.current:
                    img_ref.current.width = asset.width
                    img_ref.current.height = asset.height
                    img_ref.current.src = asset.temp_path
                    img_ref.current.visible = True
                if size_changed and grid_canvas_ref.current:
                    grid_canvas_ref.current.width = asset.width
                    grid_canvas_ref.current.height = asset.height

                if counter_ref.current:
                    counter_ref.current.value = f"{idx + 1} / {len(bmp_paths)}"
                if name_ref.current:
                    name_ref.current.value = os.path.basename(bmp_paths[idx])

                if old_bmp and old_bmp != asset.temp_path:
                    self._remove_temp_file(old_bmp)

                self.page.update()
                await apply_fit_async()
                self.page.update()
            finally:
                if loading_ref.current:
                    loading_ref.current.visible = False
                    loading_ref.current.update()

        def update_view():
            state["load_generation"] += 1
            self.page.run_task(load_current_image_async)

        def on_prev(_e):
            state["idx"] = (state["idx"] - 1) % len(bmp_paths)
            update_view()

        def on_next(_e):
            state["idx"] = (state["idx"] + 1) % len(bmp_paths)
            update_view()

        def cleanup():
            state["load_generation"] += 1
            clear_grid_cache()
            self.page.window.full_screen = state["prev_window_full_screen"]
            if overlay in self.page.overlay:
                self.page.overlay.remove(overlay)
            cleanup_viewer_temps()
            self.page.update()

        def on_close(_e=None):
            self._close_image_viewer()

        total = len(bmp_paths)
        overlay = ft.Container(
            ref=overlay_ref,
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
            content=ft.Stack(
                expand=True,
                alignment=ft.Alignment(0, 0),
                controls=[
                    ft.Container(
                        ref=panel_ref,
                        width=VIEWER_PANEL_WIDTH,
                        height=VIEWER_PANEL_HEIGHT,
                        bgcolor=ft.Colors.WHITE,
                        border_radius=8,
                        padding=VIEWER_PANEL_PADDING,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                        content=ft.Column(
                            expand=True,
                            spacing=0,
                            controls=[
                                ft.Container(
                                    ref=header_ref,
                                    height=VIEWER_HEADER_HEIGHT,
                                    bgcolor=ft.Colors.WHITE,
                                    alignment=ft.Alignment(-1, 0),
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
                            ref=viewer_area_ref,
                            expand=True,
                            clip_behavior=ft.ClipBehavior.HARD_EDGE,
                            content=ft.Stack(
                                expand=True,
                                controls=[
                                    # NOTE: alignment は Flet 0.85 クライアントの
                                    # デシリアライズ不具合でグレー画面になるため
                                    # 使用しない（中央寄せは pan() で行う）
                                    ft.InteractiveViewer(
                                        ref=viewer_ref,
                                        expand=True,
                                        constrained=False,
                                        min_scale=VIEWER_MIN_SCALE,
                                        max_scale=VIEWER_MAX_SCALE,
                                        boundary_margin=ft.Margin.all(
                                            100000,
                                        ),
                                        # -1 = 全ての更新イベントを受信する。
                                        # クライアントの判定は
                                        # 「now - 前回 > interval」のため 0 でも
                                        # 同一ミリ秒内のイベントが破棄される。
                                        # 高倍率時はフレームが長くなり複数の
                                        # ホイールティックが同一ミリ秒内に処理
                                        # されるので、間引かれると変換行列の
                                        # 追跡がずれてグリッド位置を誤る。
                                        interaction_update_interval=-1,
                                        # パン後の慣性移動はイベント通知されず
                                        # 変換追跡がずれるため、慣性を実質
                                        # 無効化する。FrictionSimulation は
                                        # 係数が小さいほど即停止する点に注意
                                        # （0.01 はデフォルトの約2.4倍も
                                        # 慣性が伸びる誤設定だった）
                                        interaction_end_friction_coefficient=(
                                            FLING_FRICTION
                                        ),
                                        trackpad_scroll_causes_scale=True,
                                        on_interaction_start=on_interaction_start,
                                        on_interaction_update=on_interaction_update,
                                        on_interaction_end=on_interaction_end,
                                        content=ft.Stack(
                                            ref=stack_ref,
                                            width=1,
                                            height=1,
                                            controls=[
                                                ft.Image(
                                                    ref=img_ref,
                                                    src="",
                                                    width=1,
                                                    height=1,
                                                    fit=ft.BoxFit.FILL,
                                                    filter_quality=(
                                                        ft.FilterQuality.NONE
                                                    ),
                                                    visible=False,
                                                ),
                                                cv.Canvas(
                                                    ref=grid_canvas_ref,
                                                    width=1,
                                                    height=1,
                                                    shapes=[],
                                                    visible=False,
                                                ),
                                            ],
                                        ),
                                    ),
                                    ft.Container(
                                        ref=loading_ref,
                                        expand=True,
                                        visible=True,
                                        bgcolor=ft.Colors.with_opacity(
                                            0.65, ft.Colors.WHITE
                                        ),
                                        content=ft.Column(
                                            [
                                                ft.ProgressRing(
                                                    width=28,
                                                    height=28,
                                                    stroke_width=3,
                                                ),
                                                ft.Text(
                                                    "読み込み中...",
                                                    size=12,
                                                    color=ft.Colors.GREY_600,
                                                ),
                                            ],
                                            alignment=ft.MainAxisAlignment.CENTER,
                                            horizontal_alignment=(
                                                ft.CrossAxisAlignment.CENTER
                                            ),
                                            spacing=10,
                                        ),
                                    ),
                                ],
                            ),
                        ),
                        ft.Container(
                            ref=footer_ref,
                            height=VIEWER_FOOTER_HEIGHT,
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
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Container(
                                        alignment=ft.Alignment(0, 0),
                                        content=ft.Row(
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
                                                    on_click=zoom_out_click,
                                                ),
                                                ft.IconButton(
                                                    icon=ft.Icons.ZOOM_IN,
                                                    tooltip="拡大",
                                                    on_click=zoom_in_click,
                                                ),
                                                ft.IconButton(
                                                    icon=ft.Icons.CROP_ORIGINAL,
                                                    tooltip="等倍表示 (100%)",
                                                    on_click=zoom_to_original_click,
                                                ),
                                                ft.IconButton(
                                                    icon=ft.Icons.FIT_SCREEN,
                                                    tooltip="全体表示にリセット",
                                                    on_click=reset_zoom,
                                                ),
                                                ft.IconButton(
                                                    ref=grid_toggle_btn_ref,
                                                    icon=ft.Icons.GRID_ON,
                                                    tooltip="ピクセルグリッドを非表示",
                                                    on_click=toggle_grid,
                                                ),
                                                ft.PopupMenuButton(
                                                    content=ft.Container(
                                                        width=52,
                                                        height=36,
                                                        border=ft.Border.all(
                                                            1, ft.Colors.GREY_400,
                                                        ),
                                                        border_radius=4,
                                                        padding=ft.Padding.symmetric(
                                                            horizontal=6,
                                                        ),
                                                        content=ft.Row(
                                                            [
                                                                ft.Text(
                                                                    ref=grid_spacing_text_ref,
                                                                    value=(
                                                                        f"{DEFAULT_VIEWER_GRID_SPACING}px"
                                                                    ),
                                                                    size=12,
                                                                ),
                                                                ft.Icon(
                                                                    ft.Icons.ARROW_DROP_DOWN,
                                                                    size=16,
                                                                    color=ft.Colors.GREY_700,
                                                                ),
                                                            ],
                                                            alignment=(
                                                                ft.MainAxisAlignment.SPACE_BETWEEN
                                                            ),
                                                            vertical_alignment=(
                                                                ft.CrossAxisAlignment.CENTER
                                                            ),
                                                        ),
                                                    ),
                                                    tooltip="グリッド間隔",
                                                    items=grid_spacing_menu_items(),
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
                                            alignment=(
                                                ft.MainAxisAlignment.CENTER
                                            ),
                                            run_alignment=(
                                                ft.MainAxisAlignment.CENTER
                                            ),
                                            wrap=True,
                                        ),
                                    ),
                                ],
                                horizontal_alignment=(
                                    ft.CrossAxisAlignment.STRETCH
                                ),
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=2,
                            ),
                        ),
                    ],
                ),
                    ),
                ],
            ),
        )

        self._image_viewer_cleanup = cleanup
        self.page.overlay.append(overlay)
        self.page.update()
        self.page.run_task(load_current_image_async)

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

    def _is_multi_task_file(self) -> bool:
        return len(self._option2_task_folders) > 1

    def _pick_option3_folder(self, e):
        async def _run():
            folder = await asyncio.to_thread(select_folder_dialog)
            if folder and self.option3_folder_field.current:
                self.option3_folder_field.current.value = folder
                self.config_manager.set("option3_folder", folder)
                self.config_manager.save()
                self._update_load_task_list_button()
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
        self._local_task_folders = []
        self._local_selected_task_prefix = None
        self._preview_source = "zip"
        self._preview_img_folder = ""
        self._local_task_list_loading = False
        self._current_task_save_jobs = []
        self._current_cleanup_paths = []

        if option == "option1":
            self.dynamic_content.current.controls.extend(
                self._build_group_task_fields())
        elif option == "option2":
            self.dynamic_content.current.controls.extend(
                self._build_option2_fields())
            self._update_option2_save_task_controls()
        elif option == "option3":
            self.dynamic_content.current.controls.extend(
                self._build_option3_fields())
        if self.preview_limit_menu.current:
            if option == "option2":
                file_path = (
                    self.file_path.current.value
                    if self.file_path.current else ""
                )
                self.preview_limit_menu.current.disabled = not file_path
            else:
                self.preview_limit_menu.current.disabled = True
        self.page.update()

    def _build_group_task_fields(self, *, include_preview: bool = True):
        """グループ番号・タスク番号入力フィールドを生成"""
        fields = [
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
        if include_preview:
            fields.extend(self._build_local_task_preview_section())
        return fields

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

    def _build_thumbnail_tile(self, img_bytes: bytes, index: int):
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

    def _build_thumbnail_panel_content(self, empty_message: str) -> tuple[list, str]:
        thumbnail_controls = []
        if self._file_thumbnails:
            for i, img_bytes in enumerate(self._file_thumbnails):
                thumbnail_controls.append(
                    self._build_thumbnail_tile(img_bytes, i)
                )
        else:
            thumbnail_controls.append(
                ft.Text(
                    empty_message,
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
        return thumbnail_controls, info_text

    def _build_task_preview_workspace(
        self,
        *,
        show_save_controls: bool,
        task_list_ref: ft.Ref[ft.Column],
        workspace_ref: ft.Ref[ft.Container],
        empty_message: str,
        list_placeholder: str,
    ) -> ft.Container:
        thumbnail_controls, info_text = self._build_thumbnail_panel_content(
            empty_message,
        )
        panel_border = ft.Border.all(1, ft.Colors.GREY_200)
        panel_radius = 6

        left_controls: list[ft.Control] = [
            ft.Text(
                (
                    "保存対象タスク（行クリックでプレビュー切替）"
                    if show_save_controls
                    else "タスク一覧（行クリックでプレビュー切替）"
                ),
                size=11,
                weight=ft.FontWeight.W_500,
            ),
            *self._build_preview_limit_row(),
        ]

        if show_save_controls:
            left_controls.extend([
                ft.Container(
                    height=26,
                    content=ft.RadioGroup(
                        ref=self.option2_save_mode_radio,
                        value="all",
                        on_change=self._on_option2_save_mode_changed,
                        content=ft.Row([
                            ft.Radio(
                                value="all",
                                label="全タスク",
                                label_style=ft.TextStyle(size=11),
                                visual_density=ft.VisualDensity.COMPACT,
                            ),
                            ft.Radio(
                                value="selected",
                                label="選択のみ",
                                label_style=ft.TextStyle(size=11),
                                visual_density=ft.VisualDensity.COMPACT,
                            ),
                        ], spacing=4, tight=True),
                    ),
                ),
                ft.Row([
                    ft.TextButton(
                        "全選択",
                        ref=self.option2_select_all_btn,
                        disabled=True,
                        style=ft.ButtonStyle(
                            padding=ft.Padding.all(4)),
                        on_click=lambda e:
                            self._set_option2_group_task_checked(True)),
                    ft.TextButton(
                        "全解除",
                        ref=self.option2_deselect_all_btn,
                        disabled=True,
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
            ])
        else:
            left_controls.append(
                ft.ElevatedButton(
                    LOAD_TASK_LIST_BUTTON_LABEL,
                    ref=self.load_task_list_btn,
                    icon=ft.Icons.REFRESH,
                    on_click=self._on_load_task_list_click,
                    disabled=not self._is_load_task_list_enabled(),
                )
            )

        left_controls.append(
            ft.Container(
                expand=True,
                content=ft.Column(
                    ref=task_list_ref,
                    controls=[
                        ft.Text(
                            list_placeholder,
                            size=11,
                            color=ft.Colors.GREY_500,
                        )
                    ],
                    spacing=2,
                    scroll=ft.ScrollMode.AUTO,
                ),
            )
        )

        return ft.Container(
            ref=workspace_ref,
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
                        content=ft.Column(
                            left_controls,
                            spacing=6,
                            expand=True,
                        ),
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
        )

    def _build_option2_fields(self):
        return [
            self._build_browse_row(
                self.file_path,
                "タスクファイル (.ziq 等)",
                self._pick_file,
            ),
            self._build_task_preview_workspace(
                show_save_controls=True,
                task_list_ref=self.option2_task_selection_column,
                workspace_ref=self.option2_workspace,
                empty_message="ファイルを選択するとプレビューが表示されます",
                list_placeholder="タスクファイルを選択してください。",
            ),
        ]

    def _build_local_task_preview_section(self):
        return [
            ft.Container(height=5),
            self._build_task_preview_workspace(
                show_save_controls=False,
                task_list_ref=self.local_task_selection_column,
                workspace_ref=self.local_task_workspace,
                empty_message=LOCAL_TASK_LIST_PLACEHOLDER,
                list_placeholder=LOCAL_TASK_LIST_PLACEHOLDER,
            ),
        ]

    def _build_option3_fields(self):
        fields = self._build_group_task_fields(include_preview=False)
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
        fields.extend(self._build_local_task_preview_section())
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

                    ft.Text("画質を選択 (100は元画像(bmp)で保存)",
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
        expanded = self._sidebar_expanded
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
            ref=self.sidebar_container,
            width=SIDEBAR_WIDTH_EXPANDED if expanded else SIDEBAR_WIDTH_COLLAPSED,
            bgcolor=ft.Colors.GREY_100,
            padding=(
                ft.Padding(left=15, right=15, top=15, bottom=15)
                if expanded
                else ft.Padding(left=0, right=0, top=8, bottom=8)
            ),
            alignment=ft.Alignment(-1, -1),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.IconButton(
                                ref=self.sidebar_toggle,
                                icon=(
                                    ft.Icons.CHEVRON_LEFT
                                    if expanded
                                    else ft.Icons.CHEVRON_RIGHT
                                ),
                                tooltip=(
                                    "サイドバーを折りたたむ"
                                    if expanded
                                    else "サイドバーを表示"
                                ),
                                on_click=self._toggle_sidebar,
                                icon_size=20,
                                style=ft.ButtonStyle(padding=0),
                            ),
                        ],
                        alignment=(
                            ft.MainAxisAlignment.END
                            if expanded
                            else ft.MainAxisAlignment.CENTER
                        ),
                    ),
                    ft.Container(
                        ref=self.sidebar_content,
                        visible=expanded,
                        expand=True,
                        content=ft.Column(
                            sidebar_controls,
                            scroll=ft.ScrollMode.AUTO,
                            alignment=ft.MainAxisAlignment.START,
                        ),
                    ),
                ],
                expand=True,
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
