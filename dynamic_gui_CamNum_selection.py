import tkinter as tk
from tkinter import ttk
from collections import defaultdict

# 2次元配列をラベルとチェックボックスのパラメータに変換する関数
def convert_arrays_to_params(arrays):
    labels_dict = defaultdict(list)

    # 配列のキーと値を辞書に追加
    for key, value in arrays:
        labels_dict[key].append(value)

    # ラベルのパラメータを作成
    label_params = [f"カメラ {key}" for key in labels_dict.keys()]
    # チェックボックスのパラメータを作成
    checkbox_params = [values for values in labels_dict.values()]

    return label_params, checkbox_params

# GUIを作成する関数
def create_gui(arrays):
    label_params, checkbox_params = convert_arrays_to_params(arrays)
    selected_items = {i: checkbox_params[i][:] for i in range(len(checkbox_params))}
    check_vars = {i: [] for i in range(len(checkbox_params))}
    result_labels = []
    result = None  # 選択された値を保持する変数

    # 選択結果を更新する関数
    def update_selection():
        for i, label in enumerate(result_labels):
            selected_values = selected_items[i]
            # 選択されたアイテムを文字列に変換して表示
            formatted_text = f"Label {i + 1} selected:\n" + "\n".join(map(str, selected_values))
            label.config(text=formatted_text)

    # チェックボックスの選択イベントのコールバック関数
    def on_checkbox_select(var, label_index, item):
        if var.get():
            selected_items[label_index].append(item)
        else:
            selected_items[label_index].remove(item)
        update_selection()

    # 全てのチェックボックスを選択する関数
    def select_all(label_index):
        for var in check_vars[label_index]:
            var.set(True)
            if var._original_value not in selected_items[label_index]:
                selected_items[label_index].append(var._original_value)
        update_selection()

    # 全てのチェックボックスの選択を解除する関数
    def deselect_all(label_index):
        for var in check_vars[label_index]:
            var.set(False)
        selected_items[label_index] = []
        update_selection()

    # OKボタンが押されたときの処理
    def on_ok():
        nonlocal result
        print("OK clicked")
        result = []
        for i, items in selected_items.items():
            for item in items:
                result.append([i + 1, item])
        print("Selected items in original format:", result)
        root.destroy()

    # Cancelボタンが押されたときの処理
    def on_cancel():
        nonlocal result
        print("Cancel clicked")
        result = None  # キャンセルが押された場合はNoneを設定
        root.destroy()

    # メインウィンドウの作成
    root = tk.Tk()
    root.title("保存したいカメラ番号、列番号を選択してください。")

    # スタイルの設定
    style = ttk.Style()
    style.configure("TCheckbutton", font=("Helvetica", 12), padding=5)
    style.configure("TButton", font=("Helvetica", 12))
    style.configure("TLabelframe.Label", font=("Helvetica", 14, "bold"))  # LabelFrameのフォントサイズを設定

    # パラメータに基づいてラベルとチェックボックスを作成
    for i, (label_text, items) in enumerate(zip(label_params, checkbox_params)):
        frame = ttk.LabelFrame(root, text=label_text, padding=(10, 10), style="TLabelframe")
        frame.grid(row=0, column=i, padx=10, pady=10, sticky="nsew")

        # 「全て選択」と「全て解除」ボタンを追加
        select_all_button = ttk.Button(frame, text="全て選択", command=lambda i=i: select_all(i))
        select_all_button.pack(anchor="w", padx=5, pady=2)

        deselect_all_button = ttk.Button(frame, text="全て解除", command=lambda i=i: deselect_all(i))
        deselect_all_button.pack(anchor="w", padx=5, pady=2)

        # 各チェックボックスを作成
        for item in items:
            item_str = str(item)
            var = tk.BooleanVar(value=True)  # 初期状態で選択
            var._original_value = item  # 元の値を保持
            check_vars[i].append(var)
            checkbox = ttk.Checkbutton(frame, text=item_str, variable=var, style="TCheckbutton", command=lambda v=var, i=i, item=item: on_checkbox_select(v, i, item))
            checkbox.pack(anchor="w", padx=5, pady=2)

        """
        # 各ラベルごとに結果を表示するラベルを作成
        result_label = tk.Label(frame, text=f"Label {i + 1} selected:", justify=tk.LEFT, anchor="w", font=("Helvetica", 12))
        result_label.pack(anchor="w", padx=5, pady=5)
        result_labels.append(result_label)
        """
        
    # 初期状態の選択結果を更新
    update_selection()

    # OKボタンとCancelボタンを作成
    button_frame = ttk.Frame(root)
    button_frame.grid(row=1, column=0, columnspan=len(label_params), pady=10, sticky="e")

    cancel_button = ttk.Button(button_frame, text="Cancel", command=on_cancel, width=10)
    cancel_button.pack(side="right", padx=10)

    ok_button = ttk.Button(button_frame, text="OK", command=on_ok, width=10)
    ok_button.pack(side="right", padx=10)

    # メインループの開始
    root.mainloop()

    return result  # 選択された値またはNoneを返す

if __name__ == "__main__":
    # 2次元配列の例
    arrays = [[1, 1], [1, 2], [1, 3], [1, 4], [2, 1], [2, 2], [2, 3], [2, 4], [2, 5], [2, 6]]
    result = create_gui(arrays)
    print("Result from main:", result)
