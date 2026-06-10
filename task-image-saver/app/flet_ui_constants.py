"""
Flet UI 用の表示テキスト・定数（フレームワーク非依存）。
"""

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

DEFAULT_FILENAME_TEMPLATES = {
    "template1": "{comment}_{index}",
    "template2": "{comment}_{tool}",
    "template3": "{original}",
}

PREVIEW_LIMIT_OPTIONS = ("6", "12", "24", "48", "96", "すべて")
DEFAULT_PREVIEW_LIMIT = "12"

SIDEBAR_WIDTH_EXPANDED = 220
SIDEBAR_WIDTH_COLLAPSED = 36
SIDEBAR_COLLAPSED_STORAGE_KEY = "sidebar_collapsed"

# Option2「表示上限」行（ラベル＋選択ボックス）
PREVIEW_LIMIT_BOX_WIDTH = 96
PREVIEW_LIMIT_ROW_HEIGHT = 28
PREVIEW_LIMIT_ROW_BOTTOM_GAP = 10
PREVIEW_LIMIT_TEXT_SIZE = 12
