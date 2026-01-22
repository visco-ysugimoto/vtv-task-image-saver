import tkinter as tk
from tkinter import ttk

def show_selection_window():
    def on_ok_button_click():
        nonlocal selected_mode, selected_option, scale_value
        selected_mode = radio_value1.get()
        selected_option = radio_value2.get()
        scale_value = scale.get()  # スケールバーの値を取得
        root.quit()  # ウィンドウを閉じる

    # メインウィンドウの設定
    root = tk.Tk()
    root.title("タスク画像保存フロー")
    root.geometry("500x500")  # ウィンドウのサイズを調整しました

    # フォント設定
    style = ttk.Style()
    style.configure("TLabel", font=("MSゴシック", 14))
    style.configure("TRadiobutton", font=("MSゴシック", 12))
    style.configure("TButton", font=("MSゴシック", 12))

    # 初期値としてNoneを設定
    selected_mode = None
    selected_option = None
    scale_value = None

    # ラベル1とフレームで区切られたラジオボタン3つ
    label1 = ttk.Label(root, text="保存モード")
    label1.pack(pady=(15, 10))  # パディングを調整

    frame1 = ttk.Frame(root, padding=10, relief="solid")  # 1段目のラジオボタン用のフレームを作成
    frame1.pack(pady=(10, 5), padx=20, fill="x")

    radio_value1 = tk.StringVar(value="0")

    radio1 = ttk.Radiobutton(frame1, text="全ての画像を保存", variable=radio_value1, value="0")
    radio2 = ttk.Radiobutton(frame1, text="コメント付き画像を保存", variable=radio_value1, value="1")
    radio3 = ttk.Radiobutton(frame1, text="ロック画像を保存", variable=radio_value1, value="2")

    radio1.pack(anchor=tk.W, pady=2)  # 左寄せとパディングを調整
    radio2.pack(anchor=tk.W, pady=2)
    radio3.pack(anchor=tk.W, pady=2)

    # ラベル2とフレームで区切られたラジオボタン2つ
    label2 = ttk.Label(root, text="カメラ列保存モード")
    label2.pack(pady=(20, 5))

    frame2 = ttk.Frame(root, padding=10, relief="solid")  # 2段目のラジオボタン用のフレームを作成
    frame2.pack(pady=(10, 5), padx=20, fill="x")

    radio_value2 = tk.StringVar(value="0")

    radio4 = ttk.Radiobutton(frame2, text="全てのカメラ列", variable=radio_value2, value="0")
    radio5 = ttk.Radiobutton(frame2, text="保存するカメラ列を選択", variable=radio_value2, value="1")

    radio4.pack(anchor=tk.W, pady=2)  # 左寄せとパディングを調整
    radio5.pack(anchor=tk.W, pady=2)

    # スケールバーの追加
    label3 = ttk.Label(root, text="圧縮率を選択(100は元画像(bmp)で保存)")
    label3.pack(pady=(20, 5))

    scale = tk.Scale(root, from_=10, to=100, orient=tk.HORIZONTAL, length=400, tickinterval=10, resolution=10)
    scale.set(100)  # スケールバーの初期値を100に設定
    scale.pack(pady=(10, 5))

    # OKとキャンセルボタン
    button_frame = ttk.Frame(root)
    button_frame.pack(pady=(30, 10))

    ok_button = ttk.Button(button_frame, text="OK", command=on_ok_button_click)
    cancel_button = ttk.Button(button_frame, text="キャンセル", command=root.quit)

    ok_button.pack(side=tk.LEFT, padx=10)
    cancel_button.pack(side=tk.LEFT, padx=10)

    root.mainloop()
    root.destroy()  # ウィンドウを破棄
    # ウィンドウが閉じられた後に値を返す
    return selected_mode, selected_option, scale_value

# スクリプトが直接実行された場合の処理
if __name__ == "__main__":
    selected_mode, selected_option, scale_value = show_selection_window()
    print(f"選択されたモード: {selected_mode}")
    print(f"選択されたオプション: {selected_option}")
    print(f"選択されたスケール値: {scale_value}")
