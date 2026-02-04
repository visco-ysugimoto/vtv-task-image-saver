import flet as ft
import os
import sys
from PIL import Image
import shutil
import zipfile
import json
import threading
import traceback
import time
import asyncio
import re
from datetime import datetime
import save_task_images_CamNum_selection
from collections import defaultdict

# tkinterのfiledialogを使用
import tkinter as tk
from tkinter import filedialog

# スクリプトの実行ディレクトリを取得
script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(script_dir, "共有VTVフォルダパス.json")


def load_config():
    """設定を読み込む関数"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as file:
            print("Config file is loaded to:", os.path.abspath(CONFIG_FILE))
            return json.load(file)
    return {}


def save_config(config):
    """設定を保存する関数"""
    with open(CONFIG_FILE, "w") as file:
        print("Config file will be saved to:", os.path.abspath(CONFIG_FILE))
        json.dump(config, file, indent=4)


def format_value(value):
    """1桁の数字に対して、先頭に0を付ける関数"""
    try:
        return f"{int(value):02}"
    except (ValueError, TypeError):
        return "00"


def convert_bmp_to_jpeg(folder, quality=85, progress_callback=None, cancel_check=None):
    """
    指定フォルダ内のBMPファイルをJPEGに変換し、元のBMPファイルを削除する関数。
    
    Args:
        progress_callback: 進捗を報告するコールバック関数 (current, total, message) -> None
        cancel_check: キャンセル状態をチェックするコールバック関数 () -> bool
    """
    if not os.path.exists(folder):
        print(f"Folder '{folder}' does not exist. No files were converted.")
        return

    # BMPファイルのリストを取得
    bmp_files = [f for f in os.listdir(folder) if f.endswith(".bmp")]
    total_files = len(bmp_files)
    
    for i, filename in enumerate(bmp_files):
        # キャンセルチェック
        if cancel_check and cancel_check():
            print("圧縮処理がキャンセルされました")
            if progress_callback:
                progress_callback(i, total_files, "キャンセルされました")
            return
        
        if progress_callback:
            progress_callback(i, total_files, f"圧縮中: {filename}")
            
        bmp_path = os.path.join(folder, filename)
        jpg_filename = filename.replace(".bmp", ".jpg")
        jpg_path = os.path.join(folder, jpg_filename)

        with Image.open(bmp_path) as img:
            img = img.convert("RGB")
            img.save(jpg_path, "JPEG", quality=quality)

        print(f"Converted {filename} to {jpg_filename} with quality={quality}")

        try:
            os.unlink(bmp_path)
            print(f"Deleted original BMP file: {filename}")
        except Exception as e:
            print(f"Failed to delete {filename}: {e}")

    if progress_callback:
        progress_callback(total_files, total_files, "圧縮完了")
        
    print("Conversion completed!")


def select_folder_dialog():
    """tkinterでフォルダ選択ダイアログを表示"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder = filedialog.askdirectory(title="フォルダを選択")
    root.destroy()
    return folder


def select_file_dialog():
    """tkinterでファイル選択ダイアログを表示"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file = filedialog.askopenfilename(
        title="タスクファイルを選択",
        filetypes=[
            ("Task Files", "*.ziq"),
            ("Task Files", "*.zit"),
            ("Task Files", "*.zii"),
            ("All Files", "*.*"),
        ]
    )
    root.destroy()
    return file


def main(page: ft.Page):
    # ページ設定
    page.title = "タスク画像保存フロー"
    page.window.width = 650
    page.window.height = 700
    page.window.min_width = 700
    page.window.min_height = 550
    page.padding = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    
    # アイコンを設定（exe化しても参照できるように解決）
    def resolve_resource_path(filename: str) -> str | None:
        candidates = []
        # PyInstaller (onefile/onedir) の場合、sys._MEIPASS が使える
        base_meipass = getattr(sys, "_MEIPASS", None)
        if base_meipass:
            candidates.append(os.path.join(base_meipass, filename))
        # onedir の場合は exe と同階層に配置されることが多い
        candidates.append(os.path.join(os.path.dirname(sys.executable), filename))
        # 開発実行時
        candidates.append(os.path.join(script_dir, filename))

        for p in candidates:
            if p and os.path.exists(p):
                return p
        return None

    # window.icon は png 推奨。無ければ ico を試す
    icon_path = resolve_resource_path("icon_image.png") or resolve_resource_path("save_task_images.ico")
    if icon_path:
        page.window.icon = icon_path
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.BLUE,
        font_family="Yu Gothic UI",
    )

    # 設定の読み込み
    config = load_config()

    # 状態変数
    selected_option = ft.Ref[ft.RadioGroup]()
    folder_path = ft.Ref[ft.TextField]()
    file_path = ft.Ref[ft.TextField]()
    group_num_field = ft.Ref[ft.TextField]()
    task_num_field = ft.Ref[ft.TextField]()
    option3_folder_field = ft.Ref[ft.TextField]()
    warning_text = ft.Ref[ft.Text]()
    info_text = ft.Ref[ft.Text]()
    dynamic_content = ft.Ref[ft.Column]()

    # 設定ダイアログ用の状態
    save_mode_ref = ft.Ref[ft.RadioGroup]()
    camera_mode_ref = ft.Ref[ft.RadioGroup]()
    compression_slider_ref = ft.Ref[ft.Slider]()
    compression_label_ref = ft.Ref[ft.Text]()
    
    # ファイル名テンプレート用
    template1_ref = ft.Ref[ft.TextField]()  # コメントあり + 画像取込XX形式
    template2_ref = ft.Ref[ft.TextField]()  # コメントあり + その他
    template3_ref = ft.Ref[ft.TextField]()  # コメントなし
    template1_preview_ref = ft.Ref[ft.Text]()
    template2_preview_ref = ft.Ref[ft.Text]()
    template3_preview_ref = ft.Ref[ft.Text]()
    preview_comment_ref = ft.Ref[ft.TextField]()
    preview_tool_capture_ref = ft.Ref[ft.TextField]()
    preview_tool_other_ref = ft.Ref[ft.TextField]()
    preview_original_ref = ft.Ref[ft.TextField]()
    preview_cam_ref = ft.Ref[ft.TextField]()
    preview_div_ref = ft.Ref[ft.TextField]()
    preview_index_ref = ft.Ref[ft.TextField]()
    
    # 処理中フラグ（重複実行防止用）
    app_state = {
        'is_dialog_open': False
    }

    # オプション説明テキスト
    option_descriptions = {
        "option1": "現在の選択:\n\nVTV9000上のタスクから\n(オフラインPC)\n\n━━━━━━━━━━━━━━━━━━\n\nオフライン上にインストールされているVTV-9000内のタスクに格納されている画像ファイルを任意のオプションで保存します。\n\nタスクを保存しているグループ番号とタスク番号を入力してください。",
        "option2": "現在の選択:\n\nタスクファイルから\n(ziq, zit, zii)\n\n━━━━━━━━━━━━━━━━━━\n\nタスクファイル(ziq, zit, zii)に格納されている画像ファイルを任意のオプションで保存します。\n\n画像が格納されているタスクファイルを選択してください。",
        "option3": "現在の選択:\n\nVTV9000上のタスクから\n(共有VTV)\n\n━━━━━━━━━━━━━━━━━━\n\nネットワーク上にインストールされているVTV-9000内のタスクに格納されている画像ファイルを任意のオプションで保存します。\n\n共有しているVTV-9000の「viscotech」フォルダを選択してください。\nまた共有VTV-900側の画像を保存しているグループ番号とタスク番号を入力してください。",
    }

    def show_message_dialog(title: str, message: str):
        """メッセージダイアログを表示"""
        def close_dialog(e):
            dialog.open = False
            page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def show_success_dialog(output_folder_path: str):
        """保存完了ダイアログ（フォルダを開くボタン付き）"""
        def close_dialog(e):
            dialog.open = False
            page.update()

        def open_folder(e):
            try:
                if output_folder_path and os.path.exists(output_folder_path):
                    os.startfile(output_folder_path)  # Windowsでフォルダを開く
                    # フォルダを開けたらダイアログも閉じる
                    dialog.open = False
                    page.update()
                else:
                    show_message_dialog("エラー", f"保存先フォルダが見つかりません:\n{output_folder_path}")
            except Exception as ex:
                show_message_dialog("エラー", f"保存先フォルダを開けませんでした:\n{type(ex).__name__}: {ex}")

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("画像保存フロー"),
            content=ft.Column(
                [
                    ft.Text("画像が指定されたフォルダに保存されました。"),
                    ft.Container(height=5),
                    ft.Text(f"保存先: {output_folder_path}", size=11, color=ft.Colors.GREY_700),
                ],
                tight=True,
                spacing=0,
            ),
            actions=[
                ft.ElevatedButton("保存先フォルダを開く", on_click=open_folder),
                ft.TextButton("OK", on_click=close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def pick_folder(e):
        """フォルダ選択ダイアログ"""
        def select_and_update():
            folder = select_folder_dialog()
            if folder:
                folder_path.current.value = folder
                warning_text.current.value = ""
                page.update()
        
        # 別スレッドで実行してUIをブロックしない
        threading.Thread(target=select_and_update, daemon=True).start()

    def pick_file(e):
        """ファイル選択ダイアログ"""
        def select_and_update():
            file = select_file_dialog()
            if file:
                file_path.current.value = file
                page.update()
        
        threading.Thread(target=select_and_update, daemon=True).start()

    def pick_option3_folder(e):
        """Option 3用フォルダ選択ダイアログ"""
        def select_and_update():
            folder = select_folder_dialog()
            if folder:
                option3_folder_field.current.value = folder
                config["option3_folder"] = folder
                save_config(config)
                page.update()
        
        threading.Thread(target=select_and_update, daemon=True).start()

    def update_dynamic_content(e=None):
        """ラジオボタンの選択に応じて動的コンテンツを更新"""
        option = selected_option.current.value if selected_option.current else "option1"
        
        # 情報パネルの更新
        info_text.current.value = option_descriptions.get(option, "")
        
        # 動的コンテンツのクリア
        dynamic_content.current.controls.clear()

        if option == "option1":
            # Option 1: グループ番号とタスク番号
            dynamic_content.current.controls.extend([
                ft.Row([
                    ft.Text("グループ番号:", width=100, size=13),
                    ft.TextField(
                        ref=group_num_field,
                        expand=True,
                        hint_text="例: 1",
                        border_radius=6,
                        content_padding=ft.padding.only(left=10, right=10, top=6, bottom=6),
                        text_size=13,
                    ),
                    ft.Container(width=93),  # 参照ボタンと揃えるためのスペーサー
                ]),
                ft.Row([
                    ft.Text("タスク番号:", width=100, size=13),
                    ft.TextField(
                        ref=task_num_field,
                        expand=True,
                        hint_text="例: 1",
                        border_radius=6,
                        content_padding=ft.padding.only(left=10, right=10, top=6, bottom=6),
                        text_size=13,
                    ),
                    ft.Container(width=93),  # 参照ボタンと揃えるためのスペーサー
                ]),
            ])
        elif option == "option2":
            # Option 2: ファイル選択
            dynamic_content.current.controls.extend([
                ft.Text("ファイル選択 (ziq, zit, zii):", size=13),
                ft.Row([
                    ft.TextField(
                        ref=file_path,
                        expand=True,
                        hint_text="タスクファイルを選択...",
                        border_radius=6,
                        content_padding=ft.padding.only(left=10, right=10, top=6, bottom=6),
                        text_size=13,
                    ),
                    ft.ElevatedButton(
                        "参照",
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=pick_file,
                    ),
                ]),
            ])
        elif option == "option3":
            # Option 3: グループ番号、タスク番号、共有フォルダ
            dynamic_content.current.controls.extend([
                ft.Row([
                    ft.Text("グループ番号:", width=100, size=13),
                    ft.TextField(
                        ref=group_num_field,
                        expand=True,
                        hint_text="例: 1",
                        border_radius=6,
                        content_padding=ft.padding.only(left=10, right=10, top=6, bottom=6),
                        text_size=13,
                    ),
                    ft.Container(width=93),  # 参照ボタンと揃えるためのスペーサー
                ]),
                ft.Row([
                    ft.Text("タスク番号:", width=100, size=13),
                    ft.TextField(
                        ref=task_num_field,
                        expand=True,
                        hint_text="例: 1",
                        border_radius=6,
                        content_padding=ft.padding.only(left=10, right=10, top=6, bottom=6),
                        text_size=13,
                    ),
                    ft.Container(width=93),  # 参照ボタンと揃えるためのスペーサー
                ]),
                ft.Container(height=5),
                ft.Text("共有VTVフォルダ選択:", size=13),
                ft.Row([
                    ft.TextField(
                        ref=option3_folder_field,
                        expand=True,
                        value=config.get("option3_folder", ""),
                        hint_text="viscotechフォルダを選択...",
                        border_radius=6,
                        content_padding=ft.padding.only(left=10, right=10, top=6, bottom=6),
                        text_size=13,
                    ),
                    ft.ElevatedButton(
                        "参照",
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=pick_option3_folder,
                    ),
                ]),
            ])

        page.update()

    def update_compression_label(e):
        """圧縮率ラベルを更新"""
        if compression_slider_ref.current and compression_label_ref.current:
            value = int(compression_slider_ref.current.value)
            compression_label_ref.current.value = f"現在の値: {value}"
            page.update()

    def show_settings_dialog(img_folder_path: str, output_folder: str):
        """設定ダイアログを表示"""
        
        # ダイアログを開いていることをマーク
        app_state['is_dialog_open'] = True

        # プレビュー用サンプル値（YYMMDDhhmmssSSS）
        now = datetime.now()
        preview_original_default = f"{now.strftime('%y%m%d%H%M%S')}{now.microsecond // 1000:03d}"
        
        # 進捗ダイアログ用のRef
        progress_bar_ref = ft.Ref[ft.ProgressBar]()
        progress_text_ref = ft.Ref[ft.Text]()
        progress_detail_ref = ft.Ref[ft.Text]()
        progress_dialog_ref = ft.Ref[ft.AlertDialog]()
        
        # 処理状態を管理
        processing_state = {
            'is_processing': False,
            'current': 0,
            'total': 0,
            'message': '準備中...',
            'completed': False,
            'error': None,
            'started': False,  # 重複実行防止フラグ
            'cancelled': False,  # キャンセルフラグ
            'created_files': [],  # 処理中に作成されたファイルのリスト
            'output_folder': ''  # 出力フォルダパス
        }
        
        def show_progress_dialog():
            """進捗ダイアログを表示"""
            
            def on_cancel_click(e):
                """キャンセルボタンクリック時の処理"""
                processing_state['cancelled'] = True
                processing_state['message'] = 'キャンセル中...'
                print("キャンセルボタンがクリックされました")
                # ボタンを無効化
                if e.control:
                    e.control.disabled = True
                    e.control.text = "キャンセル中..."
                    page.update()
            
            progress_dialog = ft.AlertDialog(
                ref=progress_dialog_ref,
                modal=True,
                title=ft.Text("画像処理中", size=16, weight=ft.FontWeight.BOLD),
                content=ft.Container(
                    width=350,
                    content=ft.Column([
                        ft.Text(
                            ref=progress_text_ref,
                            value="準備中...",
                            size=13,
                        ),
                        ft.Container(height=10),
                        ft.ProgressBar(
                            ref=progress_bar_ref,
                            value=0,
                            width=330,
                            bar_height=8,
                            border_radius=4,
                        ),
                        ft.Container(height=5),
                        ft.Text(
                            ref=progress_detail_ref,
                            value="0 / 0 ファイル",
                            size=11,
                            color=ft.Colors.GREY_600,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
                actions=[
                    ft.OutlinedButton(
                        "キャンセル",
                        on_click=on_cancel_click,
                        style=ft.ButtonStyle(
                            color=ft.Colors.RED_700,
                        ),
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.CENTER,
            )
            page.overlay.append(progress_dialog)
            progress_dialog.open = True
            page.update()
            return progress_dialog
        
        def update_progress_ui():
            """UIを更新する"""
            try:
                if progress_bar_ref.current and progress_text_ref.current and progress_detail_ref.current:
                    progress = processing_state['current'] / processing_state['total'] if processing_state['total'] > 0 else 0
                    progress_bar_ref.current.value = progress
                    progress_text_ref.current.value = processing_state['message']
                    progress_detail_ref.current.value = f"{processing_state['current']} / {processing_state['total']} ファイル"
            except Exception as e:
                print(f"UI更新エラー: {e}")
        
        def update_progress(current, total, message):
            """進捗を更新（別スレッドから呼び出される）"""
            processing_state['current'] = current
            processing_state['total'] = total
            processing_state['message'] = message
            print(f"進捗: {current}/{total} - {message}")
        
        def close_progress_dialog():
            """進捗ダイアログを閉じる"""
            processing_state['is_processing'] = False
            try:
                if progress_dialog_ref.current:
                    progress_dialog_ref.current.open = False
            except Exception as e:
                print(f"ダイアログ閉じエラー: {e}")
        
        def show_cancel_confirm_dialog(created_files, output_folder_path):
            """キャンセル時の確認ダイアログを表示"""
            file_count = len(created_files)
            
            def delete_files(e):
                """ファイルを削除"""
                confirm_dialog.open = False
                page.update()
                
                deleted_count = 0
                for filename in created_files:
                    file_path = os.path.join(output_folder_path, filename)
                    try:
                        if os.path.exists(file_path):
                            os.unlink(file_path)
                            deleted_count += 1
                            print(f"削除: {filename}")
                    except Exception as ex:
                        print(f"削除失敗: {filename} - {ex}")
                
                show_message_dialog("キャンセル完了", f"処理がキャンセルされました。\n{deleted_count}件のファイルを削除しました。")
            
            def keep_files(e):
                """ファイルを保持"""
                confirm_dialog.open = False
                page.update()
                show_message_dialog("キャンセル完了", f"処理がキャンセルされました。\n{file_count}件のファイルは保存先に残っています。")
            
            confirm_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("キャンセル確認", size=16, weight=ft.FontWeight.BOLD),
                content=ft.Container(
                    width=350,
                    content=ft.Column([
                        ft.Text("処理がキャンセルされました。", size=13),
                        ft.Container(height=10),
                        ft.Text(f"既に {file_count} 件のファイルが保存されています。", size=13),
                        ft.Container(height=5),
                        ft.Text("これらのファイルを削除しますか？", size=13, weight=ft.FontWeight.W_500),
                    ]),
                ),
                actions=[
                    ft.ElevatedButton(
                        "削除する",
                        bgcolor=ft.Colors.RED_600,
                        color=ft.Colors.WHITE,
                        on_click=delete_files,
                    ),
                    ft.OutlinedButton(
                        "残す",
                        on_click=keep_files,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            
            page.overlay.append(confirm_dialog)
            confirm_dialog.open = True
            page.update()
        
        async def progress_monitor_async():
            """進捗を監視してUIを更新する(非同期版)"""
            print("監視タスク開始")
            loop_count = 0
            
            # 処理が完了するまでUIを更新し続ける
            while True:
                update_progress_ui()
                page.update()
                loop_count += 1
                
                # 5回ごとに状態をログ出力
                if loop_count % 5 == 0:
                    print(f"監視タスク: ループ{loop_count}回目 - is_processing={processing_state['is_processing']}, completed={processing_state['completed']}, error={processing_state['error']}")
                
                # 処理が完了、エラー、またはキャンセルの場合、ループを抜ける
                if not processing_state['is_processing']:
                    print(f"監視タスク: is_processing=False を検知 - completed={processing_state['completed']}, error={processing_state['error']}, cancelled={processing_state['cancelled']}")
                    if processing_state['completed'] or processing_state['error'] or processing_state['cancelled']:
                        print("監視タスク: ループを抜けます")
                        break
                    else:
                        print("監視タスク: completedもerrorもcancelledも設定されていないため、待機を継続")
                
                await asyncio.sleep(0.1)  # 100msごとにUIを更新
            
            print("監視タスク: 処理完了を検知、最終処理開始")
            
            # 処理完了後の最終更新
            update_progress_ui()
            page.update()
            await asyncio.sleep(0.2)
            
            # 完了/エラー/キャンセル処理
            if processing_state['cancelled']:
                print("監視タスク: キャンセル処理")
                close_progress_dialog()
                page.update()
                
                # 作成されたファイルがある場合は確認ダイアログを表示
                created_files = processing_state.get('created_files', [])
                output_folder_path = processing_state.get('output_folder', '')
                if created_files and output_folder_path:
                    print(f"作成されたファイル: {len(created_files)}件 - 確認ダイアログを表示")
                    show_cancel_confirm_dialog(created_files, output_folder_path)
                else:
                    show_message_dialog("キャンセル", "処理がキャンセルされました。")
            elif processing_state['error']:
                print(f"監視タスク: エラー処理 - {processing_state['error']}")
                close_progress_dialog()
                page.update()
                show_message_dialog("エラー", f"処理中にエラーが発生しました:\n{processing_state['error']}")
            elif processing_state['completed']:
                print("監視タスク: 完了処理")
                close_progress_dialog()
                page.update()
                show_success_dialog(processing_state.get('output_folder', ''))
            
            # 次回の実行を許可するためにフラグをリセット
            processing_state['started'] = False
            app_state['is_dialog_open'] = False
            print("監視タスク終了")
        
        def execute_image_processing(save_mode, save_cam, compression, selected_cam_list=None, filename_templates=None):
            """画像処理を実行"""
            
            # 重複実行を防止
            if processing_state['started']:
                print("警告: 処理は既に開始されています。重複実行をスキップします。")
                return
            processing_state['started'] = True
            
            # デフォルトのテンプレート
            if filename_templates is None:
                filename_templates = {
                    'template1': "{comment}_{index}",
                    'template2': "{comment}_{tool}",
                    'template3': "{original}",
                }
            
            def check_cancelled():
                """キャンセル状態をチェック"""
                return processing_state['cancelled']
            
            def run_processing():
                """別スレッドで画像処理を実行"""
                print(f"処理スレッド開始: img_folder={img_folder_path}, output={output_folder}")
                try:
                    # 画像処理を実行（事前選択されたカメラリストとテンプレートを渡す）
                    save_task_images_CamNum_selection.process_images(
                        img_folder_path, output_folder, save_mode, save_cam, 
                        preselected_cam_list=selected_cam_list,
                        progress_callback=update_progress,
                        filename_templates=filename_templates,
                        cancel_check=check_cancelled
                    )
                    
                    # キャンセルされた場合は完了フラグを立てない
                    if processing_state['cancelled']:
                        print("処理スレッド: キャンセルされました")
                        return
                    
                    print("画像処理完了")

                    # 圧縮処理
                    if 0 < compression < 100:
                        print("圧縮処理開始")
                        convert_bmp_to_jpeg(output_folder, compression, progress_callback=update_progress, cancel_check=check_cancelled)
                        
                        # キャンセルされた場合は完了フラグを立てない
                        if processing_state['cancelled']:
                            print("処理スレッド: 圧縮中にキャンセルされました")
                            return
                        
                        print("圧縮処理完了")
                    
                    print("処理スレッド: completed = True を設定")
                    processing_state['completed'] = True
                    
                except Exception as ex:
                    # キャンセルによる例外は無視
                    if processing_state['cancelled']:
                        print("処理スレッド: キャンセルによる中断")
                        return
                    
                    # エラーの詳細をコンソールに出力
                    print("=" * 50)
                    print("エラーが発生しました:")
                    traceback.print_exc()
                    print("=" * 50)
                    
                    processing_state['error'] = f"{type(ex).__name__}: {ex}"
                
                finally:
                    # 新しく作成されたファイルを特定
                    if os.path.exists(output_folder):
                        current_files = set(os.listdir(output_folder))
                        new_files = current_files - processing_state.get('existing_files', set())
                        processing_state['created_files'] = list(new_files)
                        print(f"新しく作成されたファイル: {len(new_files)}件")
                    
                    print(f"処理スレッド終了: completed={processing_state['completed']}, error={processing_state['error']}, cancelled={processing_state['cancelled']}")
                    processing_state['is_processing'] = False
            
            # 状態を初期化
            processing_state['is_processing'] = True
            processing_state['current'] = 0
            processing_state['total'] = 0
            processing_state['message'] = '準備中...'
            processing_state['completed'] = False
            processing_state['error'] = None
            processing_state['cancelled'] = False
            processing_state['created_files'] = []
            processing_state['output_folder'] = output_folder
            # started はここではリセットしない（重複防止のため）
            
            # 処理開始前の既存ファイルリストを記録
            existing_files = set()
            if os.path.exists(output_folder):
                existing_files = set(os.listdir(output_folder))
            processing_state['existing_files'] = existing_files
            
            # 進捗ダイアログを表示
            show_progress_dialog()
            
            # 別スレッドで処理を実行
            threading.Thread(target=run_processing, daemon=True).start()
            
            # 非同期で進捗監視タスクを実行（メインスレッドでUI更新）
            page.run_task(progress_monitor_async)
        
        def show_camera_selection_dialog(save_mode, compression, filename_templates):
            """カメラ選択ダイアログを表示"""
            # カメラリストを取得
            camera_arrays = save_task_images_CamNum_selection.get_camera_list(img_folder_path)
            
            if not camera_arrays:
                show_message_dialog("エラー", "カメラリストを取得できませんでした。")
                return
            
            # 2次元配列をラベルとチェックボックスのパラメータに変換
            labels_dict = defaultdict(list)
            for key, value in camera_arrays:
                labels_dict[key].append(value)
            label_params = [f"カメラ {key}" for key in labels_dict.keys()]
            checkbox_params = [values for values in labels_dict.values()]
            
            # 選択状態を管理
            selected_items = {i: checkbox_params[i][:] for i in range(len(checkbox_params))}
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
                page.update()
            
            def deselect_all(label_index):
                selected_items[label_index] = []
                for cb in checkbox_refs_dict[label_index]:
                    cb.value = False
                page.update()
            
            def on_camera_ok(e):
                result_list = []
                for i, items in selected_items.items():
                    for item in items:
                        result_list.append([i + 1, item])
                camera_dialog.open = False
                page.update()
                execute_image_processing(save_mode, "1", compression, result_list, filename_templates=filename_templates)
            
            def on_camera_cancel(e):
                camera_dialog.open = False
                app_state['is_dialog_open'] = False
                page.update()
            
            # カメラごとのカラムを作成
            camera_columns = []
            for i, (label_text, items) in enumerate(zip(label_params, checkbox_params)):
                checkboxes = []
                for item in items:
                    cb = ft.Checkbox(
                        label=str(item),
                        value=True,
                        on_change=lambda e, idx=i, itm=item: on_checkbox_change(idx, itm, e.control.value),
                    )
                    checkbox_refs_dict[i].append(cb)
                    checkboxes.append(cb)
                
                camera_container = ft.Container(
                    bgcolor=ft.Colors.GREY_100,
                    border_radius=8,
                    padding=10,
                    width=150,
                    content=ft.Column([
                        ft.Text(label_text, size=13, weight=ft.FontWeight.W_500),
                        ft.Divider(height=1),
                        ft.Row([
                            ft.TextButton("全選択", on_click=lambda e, idx=i: select_all(idx)),
                            ft.TextButton("解除", on_click=lambda e, idx=i: deselect_all(idx)),
                        ], spacing=0),
                        ft.Column(checkboxes, scroll=ft.ScrollMode.AUTO, height=200, spacing=0),
                    ], spacing=5),
                )
                camera_columns.append(camera_container)
            
            camera_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("カメラ・列番号選択", size=16, weight=ft.FontWeight.BOLD),
                content=ft.Container(
                    width=min(len(camera_columns) * 160, 600),
                    content=ft.Column([
                        ft.Text("保存したいカメラ番号、列番号を選択してください", size=12),
                        ft.Container(height=5),
                        ft.Row(camera_columns, scroll=ft.ScrollMode.AUTO, spacing=10),
                    ]),
                ),
                actions=[
                    ft.ElevatedButton("OK", bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE, on_click=on_camera_ok),
                    ft.OutlinedButton("キャンセル", on_click=on_camera_cancel),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            
            page.overlay.append(camera_dialog)
            camera_dialog.open = True
            page.update()
        
        allowed_placeholders = {"comment", "tool", "original", "cam", "div", "index"}
        placeholder_pattern = re.compile(r"\{([a-zA-Z0-9_]+)(?::[^{}]+)?\}")

        def extract_unknown_placeholders(template: str):
            """未対応プレースホルダーを抽出（{name} / {name:03} 形式対応）"""
            if not template:
                return []
            names = {m.group(1) for m in placeholder_pattern.finditer(str(template))}
            unknown = sorted([n for n in names if n not in allowed_placeholders])
            return unknown

        def _parse_int_from_textfield(tf: ft.TextField, default_value: int):
            """TextFieldからintを取得。不正ならerror_textを出してデフォルトにフォールバック。"""
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

        def build_preview(template: str, condition: int):
            """
            テンプレートのプレビュー文字列を生成。
            condition:
              1=コメントあり+画像取込XX, 2=コメントあり+その他, 3=コメントなし
            """
            # サンプル値（ユーザー入力があればそれを使用）
            sample_comment = (preview_comment_ref.current.value if preview_comment_ref.current else "ng") or "ng"
            sample_tool_capture = (preview_tool_capture_ref.current.value if preview_tool_capture_ref.current else "画像取込01") or "画像取込01"
            sample_tool_other = (preview_tool_other_ref.current.value if preview_tool_other_ref.current else "ToolA") or "ToolA"
            sample_original = (preview_original_ref.current.value if preview_original_ref.current else "260120115606036_1_1") or "260120115606036_1_1"
            sample_cam = _parse_int_from_textfield(preview_cam_ref.current, 1)
            sample_div = _parse_int_from_textfield(preview_div_ref.current, 2)
            sample_index = _parse_int_from_textfield(preview_index_ref.current, 3)

            tool_value = sample_tool_capture if condition == 1 else sample_tool_other
            comment_value = sample_comment if condition in (1, 2) else ""

            # 実処理と同じ置換ロジックを使用
            try:
                return save_task_images_CamNum_selection.apply_filename_template(
                    template=template or "",
                    comment=comment_value,
                    tool_comment=tool_value,
                    original_name=sample_original,
                    cam=sample_cam,
                    div=sample_div,
                    index=sample_index,
                )
            except Exception:
                # 例外が出た場合はそのまま返す（UIが落ちないように）
                return ""

        def refresh_template_previews():
            """テンプレートプレビューとバリデーションを更新（リアルタイム）"""
            if not (template1_ref.current and template2_ref.current and template3_ref.current):
                return

            t1 = template1_ref.current.value or ""
            t2 = template2_ref.current.value or ""
            t3 = template3_ref.current.value or ""

            # 未対応プレースホルダー検知 → error_text に出す
            for tf, template in (
                (template1_ref.current, t1),
                (template2_ref.current, t2),
                (template3_ref.current, t3),
            ):
                unknown = extract_unknown_placeholders(template)
                if unknown:
                    tf.error_text = "未対応のプレースホルダー: " + ", ".join([f"{{{n}}}" for n in unknown])
                else:
                    tf.error_text = None

            # プレビュー更新
            if template1_preview_ref.current:
                template1_preview_ref.current.value = f"プレビュー: {build_preview(t1, 1)}.bmp"
            if template2_preview_ref.current:
                template2_preview_ref.current.value = f"プレビュー: {build_preview(t2, 2)}.bmp"
            if template3_preview_ref.current:
                template3_preview_ref.current.value = f"プレビュー: {build_preview(t3, 3)}.bmp"

            page.update()

        def on_template_change(e):
            refresh_template_previews()

        def on_settings_ok(e):
            """設定ダイアログOK"""
            save_mode = save_mode_ref.current.value
            save_cam = camera_mode_ref.current.value
            compression = int(compression_slider_ref.current.value)
            
            # ファイル名テンプレートを取得
            filename_templates = {
                'template1': template1_ref.current.value if template1_ref.current else "{comment}_{index}",
                'template2': template2_ref.current.value if template2_ref.current else "{comment}_{tool}",
                'template3': template3_ref.current.value if template3_ref.current else "{original}",
            }
            
            settings_dialog.open = False
            page.update()

            if save_cam == "1":
                # カメラ選択ダイアログを表示
                show_camera_selection_dialog(save_mode, compression, filename_templates)
            else:
                # 全てのカメラを保存
                execute_image_processing(save_mode, save_cam, compression, filename_templates=filename_templates)

        def on_settings_cancel(e):
            """設定ダイアログキャンセル"""
            settings_dialog.open = False
            app_state['is_dialog_open'] = False
            page.update()

        settings_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("保存設定", size=18, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=420,
                content=ft.Column([
                    # 保存モード
                    ft.Text("保存モード", size=13, weight=ft.FontWeight.W_500),
                    ft.Container(
                        bgcolor=ft.Colors.GREY_50,
                        padding=10,
                        border_radius=8,
                        content=ft.RadioGroup(
                            ref=save_mode_ref,
                            value="0",
                            content=ft.Column([
                                ft.Radio(value="0", label="全ての画像を保存"),
                                ft.Radio(value="1", label="コメント付き画像を保存"),
                                ft.Radio(value="2", label="ロック画像を保存"),
                            ],
                            spacing=2,
                            ),
                        ),
                    ),
                    ft.Container(height=8),

                    # カメラ列保存モード
                    ft.Text("カメラ列保存モード", size=13, weight=ft.FontWeight.W_500),
                    ft.Container(
                        bgcolor=ft.Colors.GREY_50,
                        padding=10,
                        border_radius=8,
                        content=ft.RadioGroup(
                            ref=camera_mode_ref,
                            value="0",
                            content=ft.Column([
                                ft.Radio(value="0", label="全てのカメラ列"),
                                ft.Radio(value="1", label="保存するカメラ列を選択"),
                            ],
                            spacing=2,
                            ),
                        ),
                    ),
                    ft.Container(height=8),

                    # 圧縮率
                    ft.Text("圧縮率を選択 (100は元画像(bmp)で保存)", size=13, weight=ft.FontWeight.W_500),
                    ft.Container(
                        bgcolor=ft.Colors.GREY_50,
                        padding=10,
                        border_radius=8,
                        content=ft.Column([
                            ft.Slider(
                                ref=compression_slider_ref,
                                min=10,
                                max=100,
                                divisions=9,
                                value=100,
                                label="{value}",
                                on_change=update_compression_label,
                            ),
                            ft.Row([
                                ft.Text("10", size=11),
                                ft.Container(expand=True),
                                ft.Text("100", size=11),
                            ]),
                            ft.Text(
                                ref=compression_label_ref,
                                value="現在の値: 100",
                                size=11,
                                color=ft.Colors.GREY_700,
                            ),
                        ],
                        spacing=2,
                        ),
                    ),
                    ft.Container(height=8),

                    # 出力ファイル名テンプレート
                    ft.ExpansionTile(
                        title=ft.Text("出力ファイル名テンプレート", size=13, weight=ft.FontWeight.W_500),
                        expanded=False,
                        controls_padding=ft.Padding(left=10, right=10, top=0, bottom=10),
                        controls=[
                            ft.Container(
                                bgcolor=ft.Colors.GREY_50,
                                padding=10,
                                border_radius=8,
                                content=ft.Column([
                                    # 条件1: コメントあり + 画像取込XX形式
                                    ft.Text("条件1: コメントあり + 画像取込XX形式", size=11, color=ft.Colors.GREY_700),
                                    ft.TextField(
                                        ref=template1_ref,
                                        value="{comment}_{index}",
                                        dense=True,
                                        text_size=12,
                                        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                        on_change=on_template_change,
                                    ),
                                    ft.Text(
                                        ref=template1_preview_ref,
                                        value="プレビュー: ",
                                        size=10,
                                        color=ft.Colors.GREY_700,
                                    ),
                                    ft.Container(height=4),
                                    
                                    # 条件2: コメントあり + その他
                                    ft.Text("条件2: コメントあり + その他のツールコメント", size=11, color=ft.Colors.GREY_700),
                                    ft.TextField(
                                        ref=template2_ref,
                                        value="{comment}_{tool}",
                                        dense=True,
                                        text_size=12,
                                        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                        on_change=on_template_change,
                                    ),
                                    ft.Text(
                                        ref=template2_preview_ref,
                                        value="プレビュー: ",
                                        size=10,
                                        color=ft.Colors.GREY_700,
                                    ),
                                    ft.Container(height=4),
                                    
                                    # 条件3: コメントなし
                                    ft.Text("条件3: コメントなし", size=11, color=ft.Colors.GREY_700),
                                    ft.TextField(
                                        ref=template3_ref,
                                        value="{original}",
                                        dense=True,
                                        text_size=12,
                                        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                        on_change=on_template_change,
                                    ),
                                    ft.Text(
                                        ref=template3_preview_ref,
                                        value="プレビュー: ",
                                        size=10,
                                        color=ft.Colors.GREY_700,
                                    ),
                                    ft.Container(height=8),
                                    
                                    # プレースホルダー説明
                                    ft.Container(
                                        bgcolor=ft.Colors.BLUE_50,
                                        padding=8,
                                        border_radius=4,
                                        content=ft.Column([
                                            ft.Text("使用可能なプレースホルダー:", size=10, weight=ft.FontWeight.W_500),
                                            ft.Text("{comment} - 画像コメント", size=10),
                                            ft.Text("{tool} - ツールコメント", size=10),
                                            ft.Text("{original} - 元ファイル名", size=10),
                                            ft.Text("{cam} - カメラ番号", size=10),
                                            ft.Text("{div} - DIV番号（列番号）", size=10),
                                            ft.Text("{index} - 連番", size=10),
                                        ],
                                        spacing=2,
                                        ),
                                    ),
                            ft.Container(height=8),

                            # プレビュー用サンプル値（変更するとプレビューが更新されます）
                            ft.Container(
                                bgcolor=ft.Colors.GREY_100,
                                padding=8,
                                border_radius=6,
                                content=ft.Column(
                                    [
                                        ft.Text(
                                            "プレビュー用サンプル値（変更するとプレビューが更新されます）",
                                            size=10,
                                            weight=ft.FontWeight.W_500,
                                            color=ft.Colors.GREY_800,
                                        ),
                                        ft.Row(
                                            [
                                                ft.TextField(
                                                    ref=preview_comment_ref,
                                                    label="comment",
                                                    value="ng",
                                                    dense=True,
                                                    text_size=11,
                                                    content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                                    expand=True,
                                                    on_change=on_template_change,
                                                ),
                                                ft.TextField(
                                                    ref=preview_original_ref,
                                                    label="original",
                                                    value=preview_original_default,
                                                    dense=True,
                                                    text_size=11,
                                                    content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                                    expand=True,
                                                    on_change=on_template_change,
                                                ),
                                            ],
                                            spacing=8,
                                        ),
                                        ft.Row(
                                            [
                                                ft.TextField(
                                                    ref=preview_tool_capture_ref,
                                                    label="tool(画像取込)",
                                                    value="画像取込01",
                                                    dense=True,
                                                    text_size=11,
                                                    content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                                    expand=True,
                                                    on_change=on_template_change,
                                                ),
                                                ft.TextField(
                                                    ref=preview_tool_other_ref,
                                                    label="tool(その他)",
                                                    value="ToolA",
                                                    dense=True,
                                                    text_size=11,
                                                    content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                                    expand=True,
                                                    on_change=on_template_change,
                                                ),
                                            ],
                                            spacing=8,
                                        ),
                                        ft.Row(
                                            [
                                                ft.TextField(
                                                    ref=preview_cam_ref,
                                                    label="cam",
                                                    value="1",
                                                    dense=True,
                                                    text_size=11,
                                                    content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                                    expand=True,
                                                    on_change=on_template_change,
                                                ),
                                                ft.TextField(
                                                    ref=preview_div_ref,
                                                    label="div",
                                                    value="2",
                                                    dense=True,
                                                    text_size=11,
                                                    content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                                    expand=True,
                                                    on_change=on_template_change,
                                                ),
                                                ft.TextField(
                                                    ref=preview_index_ref,
                                                    label="index",
                                                    value="3",
                                                    dense=True,
                                                    text_size=11,
                                                    content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                                                    expand=True,
                                                    on_change=on_template_change,
                                                ),
                                            ],
                                            spacing=8,
                                        ),
                                    ],
                                    spacing=6,
                                ),
                            ),
                                ],
                                spacing=4,
                                ),
                            ),
                        ],
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=5,
                ),
            ),
            actions=[
                ft.ElevatedButton(
                    "OK",
                    bgcolor=ft.Colors.BLUE,
                    color=ft.Colors.WHITE,
                    on_click=on_settings_ok,
                ),
                ft.OutlinedButton(
                    "キャンセル",
                    on_click=on_settings_cancel,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        page.overlay.append(settings_dialog)
        settings_dialog.open = True
        # 初回表示時にプレビューを計算
        refresh_template_previews()
        page.update()

    def on_ok_click(e):
        """OKボタンクリック時の処理"""
        # 重複クリック防止
        if app_state['is_dialog_open']:
            print("警告: ダイアログは既に開いています。重複クリックをスキップします。")
            return
        
        option = selected_option.current.value
        img_folder_path = None
        output_folder = folder_path.current.value if folder_path.current else ""

        # 保存先フォルダのチェック
        if not output_folder:
            warning_text.current.value = "画像を保存するフォルダを選択してください"
            page.update()
            return

        if option == "option1":
            # Option 1の処理
            group_num = format_value(group_num_field.current.value if group_num_field.current else "")
            task_num = format_value(task_num_field.current.value if task_num_field.current else "")

            if group_num == "00" or task_num == "00":
                warning_text.current.value = "グループ番号とタスク番号を入力してください"
                page.update()
                return

            img_folder_path = f"C:\\viscotech\\task\\g{group_num}\\{task_num}\\img"

            if not os.path.exists(img_folder_path):
                warning_text.current.value = "imgフォルダが見つかりませんでした。"
                page.update()
                return

        elif option == "option2":
            # Option 2の処理
            task_file = file_path.current.value if file_path.current else ""
            if not task_file:
                warning_text.current.value = "タスクファイルを選択してください"
                page.update()
                return

            # ローディングダイアログを表示してタスクファイルを処理
            loading_dialog_ref = ft.Ref[ft.AlertDialog]()
            loading_text_ref = ft.Ref[ft.Text]()
            loading_result = {'img_folder_path': None, 'error': None}
            
            def show_loading_dialog():
                """ローディングダイアログを表示"""
                loading_dialog = ft.AlertDialog(
                    ref=loading_dialog_ref,
                    modal=True,
                    title=ft.Text("タスクファイル処理中", size=16, weight=ft.FontWeight.BOLD),
                    content=ft.Container(
                        width=300,
                        content=ft.Column([
                            ft.Row([
                                ft.ProgressRing(width=20, height=20, stroke_width=2),
                                ft.Text(
                                    ref=loading_text_ref,
                                    value="準備中...",
                                    size=13,
                                ),
                            ], spacing=10),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ),
                )
                page.overlay.append(loading_dialog)
                loading_dialog.open = True
                page.update()
            
            def update_loading_status(message):
                """ローディング状態を更新"""
                if loading_text_ref.current:
                    loading_text_ref.current.value = message
                    page.update()
            
            def close_loading_dialog():
                """ローディングダイアログを閉じる"""
                if loading_dialog_ref.current:
                    loading_dialog_ref.current.open = False
                    page.update()
            
            def process_task_file():
                """タスクファイルを処理（別スレッド）"""
                try:
                    update_loading_status("タスクファイルをコピー中...")
                    copied_file_path = shutil.copy(task_file, output_folder)
                    zip_file_path = os.path.splitext(copied_file_path)[0] + ".zip"
                    os.rename(copied_file_path, zip_file_path)

                    update_loading_status("タスクファイルを展開中...")
                    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
                        zip_ref.extractall(output_folder)

                    os.remove(zip_file_path)

                    update_loading_status("画像フォルダを検索中...")
                    viscotech_folder_path = os.path.join(output_folder, "viscotech")
                    
                    found_img_path = None
                    for walk_root, dirs, files in os.walk(viscotech_folder_path):
                        if "img" in dirs:
                            found_img_path = os.path.join(walk_root, "img")
                            break

                    if not found_img_path:
                        loading_result['error'] = "imgフォルダが見つかりませんでした。"
                    else:
                        loading_result['img_folder_path'] = found_img_path

                except Exception as ex:
                    loading_result['error'] = f"処理中にエラーが発生しました: {ex}"
            
            async def process_and_continue():
                """タスクファイル処理後に設定ダイアログを表示"""
                # 別スレッドで処理を実行
                process_thread = threading.Thread(target=process_task_file, daemon=True)
                process_thread.start()
                
                # 処理完了を待機
                while process_thread.is_alive():
                    await asyncio.sleep(0.1)
                
                # ローディングダイアログを閉じる
                close_loading_dialog()
                
                # 結果を確認
                if loading_result['error']:
                    warning_text.current.value = loading_result['error']
                    app_state['is_dialog_open'] = False
                    page.update()
                else:
                    # 設定ダイアログを表示
                    show_settings_dialog(loading_result['img_folder_path'], output_folder)
            
            # ローディングダイアログを表示して処理開始
            show_loading_dialog()
            page.run_task(process_and_continue)
            return  # ここでon_ok_clickを抜ける（処理はprocess_and_continueで継続）

        elif option == "option3":
            # Option 3の処理
            group_num = format_value(group_num_field.current.value if group_num_field.current else "")
            task_num = format_value(task_num_field.current.value if task_num_field.current else "")
            option3_folder = option3_folder_field.current.value if option3_folder_field.current else ""

            if group_num == "00" or task_num == "00":
                warning_text.current.value = "グループ番号とタスク番号を入力してください"
                page.update()
                return

            if not option3_folder:
                warning_text.current.value = "外部のviscotechフォルダを選択してください"
                page.update()
                return

            img_folder_path = os.path.join(option3_folder, f"task\\g{group_num}\\{task_num}\\img")

            if not os.path.exists(img_folder_path):
                warning_text.current.value = "imgフォルダが見つかりませんでした。"
                page.update()
                return

        # 設定ダイアログを表示
        warning_text.current.value = ""
        page.update()
        show_settings_dialog(img_folder_path, output_folder)

    def on_cancel_click(e):
        """終了ボタンクリック時の処理"""
        import sys
        sys.exit(0)

    # サイドバー（情報パネル）
    sidebar = ft.Container(
        width=220,
        bgcolor=ft.Colors.GREY_100,
        padding=15,
        alignment=ft.Alignment(-1, -1),  # top_left
        content=ft.Column([
            ft.Text(
                "情報パネル",
                size=14,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Divider(),
            ft.Text(
                ref=info_text,
                value=option_descriptions["option1"],
                size=11,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
        alignment=ft.MainAxisAlignment.START,
        ),
    )

    # メインコンテンツ
    main_content = ft.Container(
        expand=True,
        padding=ft.padding.only(left=20, right=20, top=15, bottom=15),
        alignment=ft.Alignment(-1, -1),  # top_left
        content=ft.Column([
            # タイトル
            ft.Text(
                "タスク画像保存フロー",
                size=20,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Container(
                height=2,
                bgcolor=ft.Colors.BLUE,
                border_radius=2,
            ),
            ft.Container(height=10),

            # インポート先選択
            ft.Text("インポート先を選択", size=14, weight=ft.FontWeight.W_500),
            ft.Container(
                bgcolor=ft.Colors.GREY_50,
                padding=10,
                border_radius=8,
                content=ft.RadioGroup(
                    ref=selected_option,
                    value="option1",
                    on_change=update_dynamic_content,
                    content=ft.Column([
                        ft.Radio(value="option1", label="VTV9000上のタスクから (オフラインPC)"),
                        ft.Radio(value="option2", label="タスクファイルから (ziq, zit, zii)"),
                        ft.Radio(value="option3", label="VTV9000上のタスクから (共有VTV)"),
                    ],
                    spacing=2,
                    ),
                ),
            ),
            ft.Container(height=8),

            # 保存先フォルダ選択
            ft.Text("画像を保存するフォルダを選択", size=14, weight=ft.FontWeight.W_500),
            ft.Row([
                ft.TextField(
                    ref=folder_path,
                    expand=True,
                    hint_text="フォルダを選択...",
                    border_radius=8,
                    content_padding=ft.padding.only(left=10, right=10, top=8, bottom=8),
                    text_size=13,
                ),
                ft.ElevatedButton(
                    "参照",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=pick_folder,
                ),
            ]),

            # 警告テキスト
            ft.Text(
                ref=warning_text,
                value="",
                color=ft.Colors.RED,
                size=11,
            ),
            ft.Container(height=5),

            # 動的コンテンツ（最小高さを設定して位置を安定させる）
            ft.Container(
                height=200,  # Option 3のコンテンツがすべて収まる高さ
                content=ft.Column(
                    ref=dynamic_content,
                    spacing=8,
                    alignment=ft.MainAxisAlignment.START,
                ),
            ),
            ft.Container(height=10),

            # ボタン
            ft.Row([
                ft.ElevatedButton(
                    "OK",
                    width=130,
                    height=40,
                    bgcolor=ft.Colors.BLUE,
                    color=ft.Colors.WHITE,
                    on_click=on_ok_click,
                ),
                ft.OutlinedButton(
                    "終了",
                    width=130,
                    height=40,
                    on_click=on_cancel_click,
                ),
            ]),
        ],
        spacing=5,
        scroll=ft.ScrollMode.AUTO,
        alignment=ft.MainAxisAlignment.START,
        ),
    )

    # レイアウト
    page.add(
        ft.Row([
            sidebar,
            ft.VerticalDivider(width=1),
            main_content,
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )

    # 初期コンテンツを設定
    update_dynamic_content()


if __name__ == "__main__":
    ft.app(target=main)  # Flet 0.80以降はft.app()内部でrun()が呼ばれる
