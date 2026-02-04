"""
ユーティリティ関数を定義するモジュール
"""
import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional
from PIL import Image


def format_value(value: str) -> str:
    """
    1桁の数字に対して、先頭に0を付ける関数
    
    Args:
        value: 数値文字列
        
    Returns:
        2桁にフォーマットされた文字列
    """
    try:
        return f"{int(value):02d}"
    except (ValueError, TypeError):
        return value


def convert_bmp_to_jpeg(folder: str, quality: int = 85) -> None:
    """
    指定フォルダ内のBMPファイルをJPEGに変換し、元のBMPファイルを削除する関数。
    
    Args:
        folder: BMPファイルが含まれるフォルダのパス（出力フォルダと同じ）
        quality: JPEG保存時の圧縮率（1～100）。デフォルトは85。
    """
    folder_path = Path(folder)
    
    # フォルダが存在しない場合は何もしない
    if not folder_path.exists():
        print(f"フォルダ '{folder}' が存在しません。変換をスキップします。")
        return
    
    converted_count = 0
    error_count = 0
    
    # フォルダ内のすべてのファイルをチェック
    for bmp_file in folder_path.glob("*.bmp"):
        try:
            jpg_file = bmp_file.with_suffix(".jpg")
            
            # 画像を開いてJPEGに変換
            with Image.open(bmp_file) as img:
                img = img.convert("RGB")  # JPEGはRGBモードをサポート
                img.save(jpg_file, "JPEG", quality=quality)
            
            # 元のBMPファイルを削除
            bmp_file.unlink()
            print(f"変換完了: {bmp_file.name} -> {jpg_file.name} (品質={quality})")
            converted_count += 1
            
        except Exception as e:
            print(f"変換エラー ({bmp_file.name}): {e}")
            error_count += 1
    
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
        
        # ファイルを指定されたフォルダにコピー
        copied_file_path = shutil.copy2(task_file_path, output_folder)
        
        # コピーしたファイルのパスを.zipに変更
        zip_file_path = Path(copied_file_path).with_suffix(".zip")
        Path(copied_file_path).rename(zip_file_path)
        
        # .zipファイルを解凍
        with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
            zip_ref.extractall(output_folder)
        
        # 解凍が完了したら元の.zipファイルを削除
        zip_file_path.unlink()
        
        # viscotechフォルダのパスを取得
        viscotech_folder_path = output_path / "viscotech"
        
        # imgフォルダのパスを再帰的に検索
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
        # Option 1: デフォルトのviscotechパスを使用
        from config import Constants
        img_path = Path(Constants.DEFAULT_VISCO_TECH_PATH) / f"g{group_num}" / task_num / "img"
    
    img_path_str = str(img_path)
    
    if Path(img_path_str).exists():
        return img_path_str
    return None
