# TaskImageSaver

VTV-9000 タスクから画像を保存する Flet アプリです。

## フォルダ構成

```
task-image-saver/
├── app/          … Python アプリ本体（UI・ロジック・ランタイム）
├── launcher/     … 配布用 PyInstaller ランチャー
├── scripts/      … ビルド・検証スクリプト
├── deploy/       … 配布 ZIP に同梱するファイル
├── assets/       … アイコン（launcher.* → ビルド時に icon.* へ同期）
├── config/       … 設定ファイルのサンプル
├── pyproject.toml
└── requirements.txt
```

### app/ の主要モジュール

| ファイル | 役割 |
|---------|------|
| `main_save_task_images_flet.py` | エントリポイント |
| `task_image_saver_ui.py` | Flet UI |
| `task_image_saver_logic.py` | 画像処理フロー |
| `app_runtime.py` / `runtime_sync.py` | 配布版のパス解決・日本語パス同期 |
| `config.py` / `utils.py` | 設定・ZIP/タスク共通処理 |

## 実行（開発）

```powershell
pip install -r requirements.txt
python .\app\main_save_task_images_flet.py
```

または `run_dev.cmd` をダブルクリック。

## 配布パッケージ作成

```cmd
package_release.cmd
```

成果物:

| 出力 | 内容 |
|------|------|
| `dist\TaskImageSaver\` | 配布フォルダ |
| `dist\TaskImageSaver_v*_win64.zip` | ZIP |

利用者向け説明は `deploy\RELEASE_README.txt`（配布フォルダ内では `README.txt`）。

再ビルドをスキップする場合:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\package_release.ps1 -SkipBuild
```

## ドラッグ＆ドロップ（Windows）

初回のみ Dropzone 入り Flet クライアントのビルドが必要です。

```cmd
build_flet_dropzone.cmd
```

## 右クリックメニュー

```powershell
.\deploy\register_task_image_saver_context_menu.ps1
```

解除:

```powershell
.\deploy\unregister_task_image_saver_context_menu.ps1
```

タスクファイルを引数に渡すと Option2 プレビューで起動します。

```powershell
python .\app\main_save_task_images_flet.py "C:\path\to\task.ziq"
```
