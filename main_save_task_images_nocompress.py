import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
import os
#from PIL import Image
import shutil
import zipfile
import json
import save_task_images_CamNum_selection
from selection_window import show_selection_window

# スクリプトの実行ディレクトリを取得
script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(script_dir, "共有VTVフォルダパス.json")
# 設定ファイルのパス
#CONFIG_FILE = "config.json"

# 設定を読み込む関数
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as file:
            # 実際の保存パスを表示
            print("Config file is loaded to:", os.path.abspath(CONFIG_FILE))
            return json.load(file)
    return {}

# 設定を保存する関数
def save_config(config):
    with open(CONFIG_FILE, "w") as file:
        # 実際の保存パスを表示
        print("Config file will be saved to:", os.path.abspath(CONFIG_FILE))
        json.dump(config, file, indent=4)

# フォルダ選択ダイアログを開き、選択されたフォルダパスを表示する関数
def select_folder():
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        folder_var.set(folder_selected)
        warning_label.config(text="")

# ファイル選択ダイアログを開き、選択されたファイルパスを表示する関数
def select_file():
    file_selected = filedialog.askopenfilename(
        filetypes=[("Task Files", "*.ziq"), ("Task Files", "*.zit"), ("Task Files", "*.zii"), ("All Files", "*.*")]
    )
    if file_selected:
        file_var.set(file_selected)

def format_value(value):
    """1桁の数字に対して、先頭に0を付ける関数"""
    return f"{int(value):02}"

def convert_bmp_to_jpeg(folder, quality=85):
    """
    指定フォルダ内のBMPファイルをJPEGに変換し、元のBMPファイルを削除する関数。
    Parameters:
    folder (str): BMPファイルが含まれるフォルダのパス（出力フォルダと同じ）
    quality (int): JPEG保存時の圧縮率（1～100）。デフォルトは85。

    Returns:
    None


    # フォルダが存在しない場合は何もしない
    if not os.path.exists(folder):
        print(f"Folder '{folder}' does not exist. No files were converted.")
        return

    # フォルダ内のすべてのファイルをチェック
    for filename in os.listdir(folder):
        if filename.endswith(".bmp"):  # BMPファイルをフィルタリング
            bmp_path = os.path.join(folder, filename)
            jpg_filename = filename.replace(".bmp", ".jpg")
            jpg_path = os.path.join(folder, jpg_filename)
            
            # 画像を開いてJPEGに変換
            with Image.open(bmp_path) as img:
                img = img.convert('RGB')  # JPEGはRGBモードをサポート
                img.save(jpg_path, 'JPEG', quality=quality)

            print(f"Converted {filename} to {jpg_filename} with quality={quality}")
            
            # 元のBMPファイルを削除
            os.remove(bmp_path)
            print(f"Deleted original BMP file: {filename}")

    print("Conversion completed!")
"""
# OKボタンが押されたときの動作を定義する関数
def on_ok():
    global root
    selected = selected_option.get()
    img_folder_path = None

    if not folder_var.get():
        warning_label.config(text="画像を保存するフォルダを選択してください")
        return
    elif selected == "Option 1":
        # 数値1と数値2が入力されているかを確認
        group_num = dynamic_frame.grid_slaves(row=0, column=1)[0].get()
        task_num = dynamic_frame.grid_slaves(row=1, column=1)[0].get()
        group_num = format_value(group_num)
        task_num = format_value(task_num)
        
        if not group_num or not task_num:
            warning_label.config(text="グループ番号とタスク番号を入力してください")
            return
        # Option 1 のパスを構築
        img_folder_path = os.path.join(f"C:\\viscotech\\task\\g{group_num}\\{task_num}\\img")

        if os.path.exists(img_folder_path):
            warning_label.config(text=f"imgフォルダのパス: {img_folder_path}")
            print("imgフォルダのパス:"+img_folder_path)
        else:
            warning_label.config(text="imgフォルダが見つかりませんでした。")

    elif selected == "Option 2":
        # ファイルが選択されているかを確認
        if not file_var.get():
            warning_label.config(text="タスクファイルを選択してください")
            return
        else:
            # ファイルを指定されたフォルダにコピーする
            try:
                # ファイルを指定されたフォルダにコピー
                copied_file_path = shutil.copy(file_var.get(), folder_var.get())
                
                # コピーしたファイルのパスを.zipに変更
                zip_file_path = os.path.splitext(copied_file_path)[0] + ".zip"
                os.rename(copied_file_path, zip_file_path)

                # .zipファイルを解凍
                with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                    zip_ref.extractall(folder_var.get())
                    
                # 解凍が完了したら元の.zipファイルを削除
                os.remove(zip_file_path)
                
                # viscotechフォルダのパスを取得
                viscotech_folder_path = os.path.join(folder_var.get(), "viscotech")

                # imgフォルダのパスを再帰的に検索
                img_folder_path = None
                for walk_root, dirs, files in os.walk(viscotech_folder_path):
                    if 'img' in dirs:
                        img_folder_path = os.path.join(walk_root, 'img')
                        break

                if img_folder_path:
                    warning_label.config(text=f"imgフォルダのパス: {img_folder_path}")
                    print("imgフォルダのパス:" + img_folder_path)
                else:
                    warning_label.config(text="imgフォルダが見つかりませんでした。")
                
                print("folder path=" + folder_var.get())
                warning_label.config(text="ファイルが正常にコピーされ、解凍されました。")
            except Exception as e:
                warning_label.config(text=f"処理中にエラーが発生しました: {e}")
                print(f"処理中にエラーが発生しました: {e}")
                return
    elif selected == "Option 3":
        # 数値1、数値2、およびフォルダが選択されているかを確認
        group_num = dynamic_frame.grid_slaves(row=0, column=1)[0].get()
        task_num = dynamic_frame.grid_slaves(row=1, column=1)[0].get()
        option3_folder = dynamic_frame.grid_slaves(row=3, column=0)[0].get()
        group_num = format_value(group_num)
        task_num = format_value(task_num)
        
        if not group_num or not task_num:
            warning_label.config(text="グループ番号とタスク番号を入力してください")
            return
        if not option3_folder:
            warning_label.config(text="外部のviscotechフォルダを選択してください")
            return
        
        # Option 3 のパスを構築
        img_folder_path = os.path.join(option3_folder, f"task\\g{group_num}\\{task_num}\\img")

        if os.path.exists(img_folder_path):
            warning_label.config(text=f"imgフォルダのパス: {img_folder_path}")
            print("imgフォルダのパス:"+img_folder_path)
        else:
            warning_label.config(text="imgフォルダが見つかりませんでした。")
    
    # 全てのチェックが通った場合、メインウィンドウを閉じて新しいGUIを起動
    if selected in ["Option 1", "Option 2", "Option 3"]:
        root.destroy()  # メインウィンドウを閉じる
        save_mode,save_cam,save_compression_ratio=show_selection_window()
        save_task_images_CamNum_selection.process_images(img_folder_path,folder_var.get(),save_mode,save_cam)
        # 選択された結果をポップアップで表示
        if 0 < save_compression_ratio < 100:
            convert_bmp_to_jpeg(folder_var.get(),save_compression_ratio)
            messagebox.showinfo("画像保存フロー", "画像を圧縮しました。")
        messagebox.showinfo("画像保存フロー", "画像が指定されたフォルダに保存されました。")

# ラジオボタンの選択に応じて、動的にウィジェットを更新する関数
def update_label(*args):
    current_option = selected_option.get()
    for widget in dynamic_frame.winfo_children():
        widget.destroy()
    if current_option == "Option 1":
        option_label.config(text="現在の選択:\nVTV9000上のタスクから(オフラインPC)\n\nオフライン上にインストールされているVTV-9000内のタスクに格納されている画像ファイルを任意のオプションで保存します。\n\nタスクを保存しているグループ番号とタスク番号を入力してください。")
        create_option1_widgets()
    elif current_option == "Option 2":
        option_label.config(text="現在の選択:\nタスクファイルから(ziq, zit, zii)\n\nタスクファイル(ziq, zit, zii)に格納されている画像ファイルを任意のオプションで保存します。\n\n画像が格納されているタスクファイルを選択してください。")
        create_option2_widgets()
    elif current_option == "Option 3":
        option_label.config(text="現在の選択:\nVTV9000上のタスクから(共有VTV)\n\nネットワーク上にインストールされているVTV-9000内のタスクに格納されている画像ファイルを任意のオプションで保存します。\n\n共有しているVTV-9000の「viscotech」フォルダを選択してください。\nまた共有VTV-900側の画像を保存しているグループ番号とタスク番号を入力してください。")
        create_option3_widgets()

# Option 1のウィジェットを作成する関数
def create_option1_widgets():
    ttk.Label(dynamic_frame, text="グループ番号:", font=font_medium).grid(row=0, column=0, padx=5, pady=5, sticky='e')
    ttk.Entry(dynamic_frame, font=font_medium).grid(row=0, column=1, padx=5, pady=5, sticky='w')
    ttk.Label(dynamic_frame, text="タスク番号:", font=font_medium).grid(row=1, column=0, padx=5, pady=5, sticky='e')
    ttk.Entry(dynamic_frame, font=font_medium).grid(row=1, column=1, padx=5, pady=5, sticky='w')

# Option 2のウィジェットを作成する関数
def create_option2_widgets():
    dynamic_frame.columnconfigure(1, weight=1)
    ttk.Label(dynamic_frame, text="ファイル選択(ziq,zit,zii):", font=font_medium).grid(row=0, column=0, padx=5, pady=5, sticky='w', columnspan=3)
    file_entry = ttk.Entry(dynamic_frame, textvariable=file_var, font=font_medium)
    file_entry.grid(row=1, column=0, padx=5, pady=5, sticky='ew', columnspan=2)
    file_button = ttk.Button(dynamic_frame, text="参照", command=select_file, width=8)
    file_button.grid(row=1, column=2, padx=5, pady=5, sticky='w')

# Option 3のウィジェットを作成する関数
def create_option3_widgets():
    dynamic_frame.columnconfigure(1, weight=1)
    # 数値入力欄の作成
    ttk.Label(dynamic_frame, text="グループ番号:", font=font_medium).grid(row=0, column=0, padx=5, pady=5, sticky='e')
    ttk.Entry(dynamic_frame, font=font_medium).grid(row=0, column=1, padx=5, pady=5, sticky='w')
    ttk.Label(dynamic_frame, text="タスク番号:", font=font_medium).grid(row=1, column=0, padx=5, pady=5, sticky='e')
    ttk.Entry(dynamic_frame, font=font_medium).grid(row=1, column=1, padx=5, pady=5, sticky='w')
    
    # フォルダ選択欄の作成
    ttk.Label(dynamic_frame, text="共有VTVフォルダ選択:", font=font_medium).grid(row=2, column=0, padx=5, pady=5, sticky='w', columnspan=3)
    
    folder_entry = ttk.Entry(dynamic_frame, textvariable=option3_folder_var, font=font_medium)
    folder_entry.grid(row=3, column=0, padx=5, pady=2, sticky='ew', columnspan=2)
    
    folder_button = ttk.Button(dynamic_frame, text="参照", command=lambda: select_folder_for_var(option3_folder_var), width=8)
    folder_button.grid(row=3, column=2, padx=5, pady=2, sticky='w')

def select_folder_for_var(folder_var):
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        folder_var.set(folder_selected)
        # フォルダ情報を保存
        config["option3_folder"] = folder_selected
        save_config(config)


# メインウィンドウの設定
root = tk.Tk()
root.title("タスク画像保存フロー")
root.geometry("700x650")

# テーマの設定
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    azure_tcl_path = os.path.join(script_dir, "azure.tcl")
    if os.path.isfile(azure_tcl_path):
        root.tk.call("source", azure_tcl_path)
        root.tk.call("set_theme", "light")
        style = ttk.Style()
    else:
        raise FileNotFoundError(f"File not found: {azure_tcl_path}")
except (tk.TclError, FileNotFoundError) as e:
    print(f"Error loading Azure theme: {e}")
    style = ttk.Style()
    style.theme_use('clam')

# フォントの設定
font_large = ("Helvetica", 14)
font_medium = ("Helvetica", 12)

# スタイルの設定
style.configure("TLabel", font=font_large)
style.configure("TRadiobutton", font=font_medium)
style.configure("TButton", font=font_medium, padding=5)
style.configure("TEntry", font=font_medium)

# メインフレームの設定
main_frame = ttk.Frame(root)
main_frame.pack(fill="both", expand=True, padx=5, pady=10)

# 左フレームの設定
left_frame = ttk.Frame(main_frame, padding=5, width=200, relief="solid", borderwidth=1, style="Custom.TFrame")
left_frame.pack(side="left", fill="y", padx=10, pady=10)
left_frame.pack_propagate(False)

# 現在の選択を表示するラベル
option_label = ttk.Label(left_frame, text="現在の選択: ", font=font_medium, wraplength=180, style="Custom.TLabel", anchor='w')
option_label.pack(pady=5, fill='x')

# セパレーターの設定
separator = ttk.Separator(main_frame, orient='vertical', style="Custom.TSeparator")
separator.pack(side="left", fill='y', padx=10, pady=10)

# 右フレームの設定
right_frame = ttk.Frame(main_frame, padding=10)
right_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

# タイトルラベルの設定
title_label = ttk.Label(right_frame, text="タスク画像保存フロー", font=font_large)
title_label.pack(pady=10)

# タイトルセパレーターの設定
title_separator = ttk.Separator(right_frame, orient='horizontal', style="Custom.TSeparator")
title_separator.pack(fill='x', pady=10)

# インポート先を選択するラベルの設定
label = ttk.Label(right_frame, text="インポート先を選択", font=font_medium)
label.pack(pady=2)

# オプションフレームの設定
option_frame = ttk.Frame(right_frame, padding=5)
option_frame.pack(pady=5, fill="x")

# ラジオボタンの設定
selected_option = tk.StringVar(value="Option 1")
selected_option.trace("w", update_label)

option1 = ttk.Radiobutton(option_frame, text="VTV9000上のタスクから(オフラインPC)", variable=selected_option, value="Option 1")
option2 = ttk.Radiobutton(option_frame, text="タスクファイルから(ziq, zit, zii)", variable=selected_option, value="Option 2")
option3 = ttk.Radiobutton(option_frame, text="VTV9000上のタスクから(共有VTV)", variable=selected_option, value="Option 3")

option1.pack(anchor='w', pady=2)
option2.pack(anchor='w', pady=2)
option3.pack(anchor='w', pady=2)

# 保存先選択フレームの設定
save_frame = ttk.Frame(right_frame, padding=10)
save_frame.pack(pady=2, fill="x")

# 保存先選択ラベルの設定
save_label = ttk.Label(save_frame, text="画像を保存するフォルダを選択", font=font_medium)
save_label.pack(anchor='w')

# フォルダ選択エントリとボタンの設定
folder_var = tk.StringVar()
file_var = tk.StringVar()

folder_entry = ttk.Entry(save_frame, textvariable=folder_var, width=25)
folder_entry.pack(side='left', padx=5, pady=2, fill="x", expand=True)

folder_button = ttk.Button(save_frame, text="参照", command=select_folder)
folder_button.pack(side='left', padx=5, pady=2)

# 警告ラベルの設定
warning_label = ttk.Label(right_frame, text="", foreground="red", font=font_medium)
warning_label.pack(pady=2)

# 動的フレームの設定
dynamic_frame = ttk.Frame(right_frame, padding=10)
dynamic_frame.pack(pady=2, fill='both', expand=True)

# ボタンフレームの設定
button_frame = ttk.Frame(right_frame, padding=10)
button_frame.pack(pady=2)

# OKボタンとキャンセルボタンの設定
ok_button = ttk.Button(button_frame, text="OK", command=on_ok, width=15)
cancel_button = ttk.Button(button_frame, text="キャンセル", command=root.quit, width=15)

ok_button.grid(row=0, column=0, padx=5, pady=5)
cancel_button.grid(row=0, column=1, padx=5, pady=10)

# カスタムスタイルの設定
style.configure("Custom.TFrame", background="#f0f0f0")
style.configure("Custom.TLabel", background="#f0f0f0", font=font_medium)
style.configure("Custom.TSeparator", background="#007acc")

# プログラム起動時に設定を読み込む
config = load_config()
option3_folder_var = tk.StringVar(value=config.get("option3_folder", ""))

# 初期ラベルの更新
update_label()  # 初期選択されているラジオボタンに応じてGUIを生成

# メインループの開始
root.mainloop()
