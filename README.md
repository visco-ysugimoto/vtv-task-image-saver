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

`TaskImageSaver` 関連は `task-image-saver` フォルダに分離しています。

Pipenvを使う場合:

```powershell
cd .\task-image-saver
pipenv install
pipenv run python .\main_save_task_images.py
```

`requirements.txt` を使う場合:

```powershell
cd .\task-image-saver
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\main_save_task_images.py
```

## 設定ファイル（共有VTVフォルダの保存）

アプリは `共有VTVフォルダパス.json` に前回選択した共有フォルダを保存します（リポジトリには含めません）。
必要なら `共有VTVフォルダパス.sample.json` をコピーして利用してください。

## ビルド（PyInstaller）

### リポジトリ直下から TaskFilePreviewer のみ exe 化

`task-file-previewer\build_task_file_previewer.ps1` をルートから呼び出すだけです（TaskImageSaver は含みません）。

```powershell
cd .\vtv-task-image-saver
.\build_all_apps.ps1
```

単一 exe にする例:

```powershell
.\build_all_apps.ps1 -BuildMode OneFile
```

コマンドプロンプトからは `build_all_apps.bat` でも同じです（引数はそのまま渡ります）。

### Flet版のビルド方法

PowerShellスクリプトを使用する場合（推奨）:

```powershell
cd .\task-image-saver
# ビルドスクリプトを実行
.\build_exe.ps1
```

手動でビルドする場合:

```powershell
cd .\task-image-saver
# 依存関係のインストール
pip install -r requirements.txt

# フォルダ版（複数ファイル、起動が速い）
pyinstaller main_save_task_images_flet.spec --noconfirm

# 単一exe版（配布が簡単、ファイルサイズ大）
pyinstaller main_save_task_images_flet_onefile.spec --noconfirm
```

ビルド成果物:
- フォルダ版: `task-image-saver\dist\TaskImageSaver\TaskImageSaver.exe`
- 単一exe版: `task-image-saver\dist\TaskImageSaver.exe`

### 旧版（tkinter版）

`task-image-saver\main_save_task_images.spec` を使ってexe化できます（生成物はコミット対象外です）。

## TaskFilePreviewer のアプリ化（単体配布向け）

TaskFilePreviewer 関連は `task-file-previewer` フォルダに分離しています。

`task_file_previewer.py` は専用スクリプトで単体exe化できます。

主な表示内容:
- タスク内 `img` の代表画像サムネイル
- ZIP 内 `viscotech/ver.txt` から読み取ったタスクバージョン
  - `ver.txt` の 1〜3 行目をバージョン、5 行目をビルド番号として扱い、例: `8.2.6B11`

```powershell
cd .\task-file-previewer
.\build_task_file_previewer.ps1
```

生成物:
- 高速起動版（推奨）:
  - 実行ファイル: `task-file-previewer\dist\TaskFilePreviewer\TaskFilePreviewer.exe`
  - 配布用zip: `task-file-previewer\dist\TaskFilePreviewer_portable_onedir.zip`
- 単一exe版:
  - 実行ファイル: `task-file-previewer\dist\TaskFilePreviewer.exe`
  - 配布用zip: `task-file-previewer\dist\TaskFilePreviewer_portable.zip`

単一exe版を作る場合:

```powershell
cd .\task-file-previewer
.\build_task_file_previewer.ps1 -BuildMode OneFile
```

補足:
- `tkinterdnd2` が同梱されるため、配布先PCに Python は不要です。
- `icon_image.ico` が存在しない場合でもビルドは継続します（標準アイコン）。
- 起動速度を重視する場合は、単一exeより `OneDir` 版（既定）を推奨します。

### 右クリックメニュー連携（アプリ未起動でも開く）

**TaskImageSaver（推奨）** — プレビュー確認後、そのまま保存フローへ進めます。

```powershell
cd .\task-image-saver
.\register_task_image_saver_context_menu.ps1
```

**TaskFilePreviewer（プレビュー専用・従来）** — 確認のみの場合。

```powershell
cd .\task-file-previewer
.\register_task_file_previewer_context_menu.ps1
```

対象拡張子は既定で `.ziq` / `.zit` / `.zii` / `.zig` / `.zia` です（`-IncludeZip` で `.zip` も追加可能）。

`dist` 以外に exe がある場合:

```powershell
cd .\task-file-previewer
.\register_task_file_previewer_context_menu.ps1 -AppPath "C:\path\to\TaskFilePreviewer.exe"
```

解除:

```powershell
cd .\task-file-previewer
.\unregister_task_file_previewer_context_menu.ps1
```

補足:
- レジストリは `HKCU` 配下のみを変更するため、管理者権限なしで実行できます。
- 右クリックから開いた場合、選択ファイルは起動時に自動読み込みされます。
- 既定では起動の速い `task-file-previewer\dist\TaskFilePreviewer\TaskFilePreviewer.exe` を優先して登録します。

