## タスク画像選択保存

VTV-9000 のタスクに含まれる画像（`img` フォルダ）を、指定したフォルダへ保存するための GUI ツールです。

## 概要

- **Option 1**: オフラインPC上の VTV-9000 タスクから取得（例: `C:\viscotech\task\gXX\YY\img`）
- **Option 2**: タスクファイル（`.ziq`/`.zit`/`.zii`）から取得（ZIPとして展開して `viscotech/**/img` を探索）
- **Option 3**: 共有VTV（ネットワーク上の `viscotech`）から取得

## 動作環境

- Windows 10 / 11（64bit）
- 開発時: Python 3.10+

## セットアップ（開発）

`TaskImageSaver` は `task-image-saver` フォルダにあります。

```powershell
cd .\task-image-saver
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\main_save_task_images_flet.py
```

## 設定ファイル（共有VTVフォルダの保存）

アプリは `共有VTVフォルダパス.json` に前回選択した共有フォルダを保存します（リポジトリには含めません）。
必要なら `task-image-saver\共有VTVフォルダパス.sample.json` をコピーして利用してください。

## 配布パッケージのビルド

```powershell
cd .\task-image-saver
.\package_release.cmd
```

または:

```powershell
powershell -ExecutionPolicy Bypass -File .\package_release.ps1
```

成果物:

- `task-image-saver\dist\TaskImageSaver\` … 配布フォルダ
- `task-image-saver\dist\TaskImageSaver_v*_win64.zip` … 配布 ZIP

詳細は `task-image-saver\README.md` を参照してください。

## 右クリックメニュー（タスクファイルのプレビュー）

```powershell
cd .\task-image-saver
.\register_task_image_saver_context_menu.ps1
```

解除:

```powershell
.\unregister_task_image_saver_context_menu.ps1
```

## TaskFilePreviewer（別アプリ）

プレビュー専用の `TaskFilePreviewer` は `task-file-previewer` フォルダに分離しています。

```powershell
cd .\task-file-previewer
.\build_task_file_previewer.ps1
```

ルートから呼び出す場合:

```powershell
.\build_all_apps.ps1
```
