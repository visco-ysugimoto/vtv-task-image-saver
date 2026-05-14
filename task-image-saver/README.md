# TaskImageSaver

このフォルダは `main_save_task_images` 系の専用領域です。

## 主要ファイル

- `main_save_task_images_flet.py`: メインアプリ（Flet）
- `main_save_task_images.py`: 旧Tk版
- `main_save_task_images_flet.spec`: Fletフォルダ版ビルド
- `main_save_task_images_flet_onefile.spec`: Flet単一exe版ビルド
- `build_exe.ps1`: ビルドスクリプト
- `config.py` / `utils.py`: 共通ロジック

## 実行

```powershell
python .\main_save_task_images_flet.py
```

## ビルド

```powershell
.\build_exe.ps1
```
