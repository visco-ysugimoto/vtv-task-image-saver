"""
設定管理と定数を定義するモジュール
"""
import os
import json
from typing import Dict, Any
from pathlib import Path


class Constants:
    """アプリケーション全体で使用する定数"""
    
    # オプション値
    OPTION_1 = "Option 1"
    OPTION_2 = "Option 2"
    OPTION_3 = "Option 3"
    
    # 保存モード
    SAVE_MODE_ALL = "0"
    SAVE_MODE_COMMENTED = "1"
    SAVE_MODE_LOCKED = "2"
    
    # カメラ保存モード
    CAM_MODE_ALL = "0"
    CAM_MODE_SELECT = "1"
    
    # デフォルトパス
    DEFAULT_VISCO_TECH_PATH = r"C:\viscotech\task"
    VISCO_TECH_FOLDER = "viscotech"
    IMG_FOLDER = "img"
    
    # ファイル拡張子
    TASK_FILE_EXTENSIONS = [("Task Files", "*.ziq"), ("Task Files", "*.zit"), 
                           ("Task Files", "*.zii"), ("All Files", "*.*")]
    BMP_EXTENSION = ".bmp"
    JPG_EXTENSION = ".jpg"
    TXT_EXTENSION = ".txt"
    
    # フォント設定
    FONT_LARGE = ("Helvetica", 14)
    FONT_MEDIUM = ("Helvetica", 12)
    
    # ウィンドウ設定
    MAIN_WINDOW_SIZE = "700x650"
    SELECTION_WINDOW_SIZE = "500x500"
    
    # JPEG品質設定
    DEFAULT_JPEG_QUALITY = 85
    MIN_JPEG_QUALITY = 1
    MAX_JPEG_QUALITY = 100
    NO_COMPRESSION_VALUE = 100


class ConfigManager:
    """設定ファイルの読み込み・保存を管理するクラス"""
    
    def __init__(self, config_file_name: str = "共有VTVフォルダパス.json"):
        """
        初期化
        
        Args:
            config_file_name: 設定ファイル名
        """
        script_dir = Path(__file__).parent.absolute()
        self.config_file = script_dir / config_file_name
        self._config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> Dict[str, Any]:
        """
        設定ファイルを読み込む
        
        Returns:
            設定辞書（ファイルが存在しない場合は空辞書）
        """
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as file:
                    self._config = json.load(file)
                    print(f"設定ファイルを読み込みました: {self.config_file}")
            except (json.JSONDecodeError, IOError) as e:
                print(f"設定ファイルの読み込みエラー: {e}")
                self._config = {}
        else:
            self._config = {}
        
        return self._config
    
    def save(self) -> None:
        """設定ファイルに保存する"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as file:
                json.dump(self._config, file, indent=4, ensure_ascii=False)
            print(f"設定ファイルを保存しました: {self.config_file}")
        except IOError as e:
            print(f"設定ファイルの保存エラー: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        設定値を取得
        
        Args:
            key: 設定キー
            default: デフォルト値
            
        Returns:
            設定値（存在しない場合はデフォルト値）
        """
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        設定値を設定
        
        Args:
            key: 設定キー
            value: 設定値
        """
        self._config[key] = value
    
    def update(self, **kwargs) -> None:
        """
        複数の設定値を一度に更新
        
        Args:
            **kwargs: 設定キーと値のペア
        """
        self._config.update(kwargs)
