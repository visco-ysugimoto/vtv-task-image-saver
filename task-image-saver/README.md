# TaskImageSaver

このフォルダは `main_save_task_images` 系の専用領域です。

## 主要ファイル

- `main_save_task_images_flet.py`: エントリポイント（Flet 起動）
- `task_image_saver_ui.py`: Flet UI（画面・ダイアログ）
- `task_image_saver_logic.py`: ビジネスロジック（画像処理フロー・プレビュー等）
- `task_image_saver_launcher.py`: 配布用ランチャー
- `runtime_sync.py`: 日本語パス向け runtime 同期（ハードリンク等）
- `flet_resources.py`: リソースパス解決・ファイルダイアログ・Win32 アイコン
- `flet_ui_constants.py`: UI 表示用テキスト定数
- `build_exe.ps1` / `package_release.ps1`: 配布ビルド
- `config.py` / `utils.py`: 設定・ZIP/タスクファイル共通処理
- `save_task_images_CamNum_selection.py`: 画像コピー・CAM 選択のコア処理

## 実行

```powershell
pip install -r requirements.txt
python .\main_save_task_images_flet.py
```

## 配布パッケージ作成

利用者に渡す ZIP を作る場合（Python / Flutter のインストール不要）:

```cmd
cd task-image-saver
package_release.cmd
```

成果物:

| 出力 | 内容 |
|------|------|
| `dist\TaskImageSaver\` | 配布フォルダ（このフォルダごとコピー） |
| `dist\TaskImageSaver_v*_win64.zip` | 上記を ZIP 化したもの |

利用者向け説明は `RELEASE_README.txt`（配布フォルダ内では `README.txt`）を同梱します。

再ビルドをスキップして既存の `build\windows` からパッケージだけ作る場合:

```powershell
powershell -ExecutionPolicy Bypass -File .\package_release.ps1 -SkipBuild
```

## 開発者向けビルド

```powershell
.\build_exe.ps1
```

（内部で `package_release.ps1` を呼び出します）

### ドラッグ＆ドロップ（Windows）

Flet の画面は別プロセス (`flet.exe`) で描画されるため、**初回のみ** ドロップ拡張入りクライアントのビルドが必要です。

**推奨（実行ポリシーの設定不要）:**

```cmd
cd task-image-saver
build_flet_dropzone.cmd
```

PowerShell で `.ps1` を使う場合（実行ポリシーでブロックされるとき）:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_flet_dropzone.ps1
```

手動で実行する場合:

```powershell
cd task-image-saver
pip install flet-dropzone flet-cli
.\sync_flet_assets.ps1   # icon_image.* → assets\icon_windows.ico 等
python -m flet_cli.cli build windows -v --yes --no-rich-output
```

ビルド後、`build\windows\task-image-saver.exe` を直接起動するか、`python main_save_task_images_flet.py` で起動できます。

タスクファイルを引数に渡すと、Option2 のプレビューを開いた状態で起動します（右クリックメニューと同じ）。

```powershell
python .\main_save_task_images_flet.py "C:\path\to\task.ziq"
```

### 右クリックメニュー（タスクファイルのプレビュー）

ビルド後の `TaskImageSaver.exe` を `.ziq` 等の右クリックから開けるように登録します（`HKCU` のみ、管理者権限不要）。

```powershell
.\register_task_image_saver_context_menu.ps1
```

解除:

```powershell
.\unregister_task_image_saver_context_menu.ps1
```

配布フォルダ内では `register_task_image_saver_context_menu.cmd` でも登録できます。
