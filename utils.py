"""
ユーティリティ関数を定義するモジュール
"""
import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional, Callable
from PIL import Image


def format_value(value: str) -> str:
    """
    1桁の数字に対して、先頭に0を付ける関数

    Args:
        value: 数値文字列

    Returns:
        2桁にフォーマットされた文字列（変換不可の場合は "00"）
    """
    try:
        return f"{int(value):02d}"
    except (ValueError, TypeError):
        return "00"


def convert_bmp_to_jpeg(folder: str, quality: int = 85,
                        progress_callback: Optional[Callable] = None,
                        cancel_check: Optional[Callable] = None) -> None:
    """
    指定フォルダ内のBMPファイルをJPEGに変換し、元のBMPファイルを削除する関数。

    Args:
        folder: BMPファイルが含まれるフォルダのパス
        quality: JPEG保存時の圧縮率（1〜100）。デフォルトは85。
        progress_callback: 進捗を報告するコールバック (current, total, message) -> None
        cancel_check: キャンセル状態をチェックするコールバック () -> bool
    """
    folder_path = Path(folder)

    if not folder_path.exists():
        print(f"フォルダ '{folder}' が存在しません。変換をスキップします。")
        return

    bmp_files = list(folder_path.glob("*.bmp"))
    total_files = len(bmp_files)
    converted_count = 0
    error_count = 0

    for i, bmp_file in enumerate(bmp_files):
        if cancel_check and cancel_check():
            print("圧縮処理がキャンセルされました")
            if progress_callback:
                progress_callback(i, total_files, "キャンセルされました")
            return

        if progress_callback:
            progress_callback(i, total_files, f"圧縮中: {bmp_file.name}")

        try:
            jpg_file = bmp_file.with_suffix(".jpg")

            with Image.open(bmp_file) as img:
                img = img.convert("RGB")
                img.save(jpg_file, "JPEG", quality=quality)

            bmp_file.unlink()
            print(f"変換完了: {bmp_file.name} -> {jpg_file.name} (品質={quality})")
            converted_count += 1

        except Exception as e:
            print(f"変換エラー ({bmp_file.name}): {e}")
            error_count += 1

    if progress_callback:
        progress_callback(total_files, total_files, "圧縮完了")

    if converted_count > 0:
        print(f"変換完了: {converted_count}個のファイルを変換しました。")
    if error_count > 0:
        print(f"警告: {error_count}個のファイルでエラーが発生しました。")


def extract_task_file(task_file_path: str, output_folder: str) -> Optional[str]:
    """
    タスクファイル（.ziq, .zit, .zii）を解凍し、imgフォルダのパスを返す

    Args:
        task_file_path: タスクファイルのパス
        output_folder: 解凍先フォルダ

    Returns:
        imgフォルダのパス（見つからない場合はNone）
    """
    try:
        output_path = Path(output_folder)

        copied_file_path = shutil.copy2(task_file_path, output_folder)

        zip_file_path = Path(copied_file_path).with_suffix(".zip")
        Path(copied_file_path).rename(zip_file_path)

        with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
            zip_ref.extractall(output_folder)

        zip_file_path.unlink()

        viscotech_folder_path = output_path / "viscotech"

        for walk_root, dirs, files in os.walk(viscotech_folder_path):
            if "img" in dirs:
                img_folder_path = Path(walk_root) / "img"
                return str(img_folder_path)

        return None

    except Exception as e:
        print(f"タスクファイルの解凍エラー: {e}")
        raise


def find_img_folder(base_path: str, group_num: str, task_num: str) -> Optional[str]:
    """
    VTV-9000のimgフォルダのパスを構築

    Args:
        base_path: ベースパス（Option 1の場合はNone、Option 3の場合は共有VTVフォルダパス）
        group_num: グループ番号（2桁フォーマット済み）
        task_num: タスク番号（2桁フォーマット済み）

    Returns:
        imgフォルダのパス
    """
    if base_path:
        img_path = Path(base_path) / "task" / f"g{group_num}" / task_num / "img"
    else:
        from config import Constants
        img_path = Path(Constants.DEFAULT_VISCO_TECH_PATH) / f"g{group_num}" / task_num / "img"

    img_path_str = str(img_path)

    if Path(img_path_str).exists():
        return img_path_str
    return None
