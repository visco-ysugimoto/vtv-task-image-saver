## タスク画像選択保存

VTV-9000 のタスクに含まれる画像（`img` フォルダ）を、指定したフォルダへ保存するためのGUIツールです。

## 概要

- **Option 1**: オフラインPC上の VTV-9000 タスクから取得（例: `C:\viscotech\task\gXX\YY\img`）
- **Option 2**: タスクファイル（`.ziq`/`.zit`/`.zii`）から取得（ZIPとして展開して `viscotech/**/img` を探索）
- **Option 3**: 共有VTV（ネットワーク上の `viscotech`）から取得

## 動作環境

- Windows
- Python 3.10+ 推奨

## セットアップ

Pipenvを使う場合:

```powershell
pipenv install
pipenv run python .\main_save_task_images.py
```

`requirements.txt` を使う場合:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\main_save_task_images.py
```

## 設定ファイル（共有VTVフォルダの保存）

アプリは `共有VTVフォルダパス.json` に前回選択した共有フォルダを保存します（リポジトリには含めません）。
必要なら `共有VTVフォルダパス.sample.json` をコピーして利用してください。

## ビルド（PyInstaller）

`main_save_task_images.spec` を使ってexe化できます（生成物はコミット対象外です）。

