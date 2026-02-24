"""
txtファイルを読み込んで、画像ファイル名の一覧を抽出・表示するテスト

txtファイルの形式:
- Comment=... (画像コメント)
- Locked=... (ロック状態: 0 or 1)
- FILE=... (画像ファイル名、複数行あり得る)

使い方:
  python test_read_txt_image_list.py                      # ユニットテストのみ実行
  python test_read_txt_image_list.py "C:\\path\\to\\file.txt"  # 指定したtxtファイルを読み込んで画像一覧を表示
"""
import os
import re
import sys
import unittest

# 同ディレクトリのモジュールをインポート
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
from save_task_images_CamNum_selection import (
    apply_filename_template,
    parse_cammaster_log_ordered,
)


def extract_image_filenames_from_txt(txt_path: str) -> list[str]:
    """
    txtファイルを読み込み、FILE=で始まる行から画像ファイル名の一覧を抽出する
    
    Args:
        txt_path: txtファイルのパス
    
    Returns:
        画像ファイル名のリスト
    """
    image_filenames = []
    if not os.path.exists(txt_path):
        return image_filenames
    
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            if 'FILE=' in line:
                file_name = line.replace('FILE=', '').strip()
                if file_name:
                    image_filenames.append(file_name)
    
    return image_filenames


def _find_cam_and_div(text: str) -> list[int]:
    """テキストからカメラ番号とDIV番号を抽出"""
    numbers = re.findall(r'\d+', text)
    return [int(n) for n in numbers[:2]]


def _adjust_save_CAM_list(save_CAM_list: list) -> list:
    """カメラリストを調整（連続するDIV番号に補正）"""
    if not save_CAM_list:
        return save_CAM_list
    adjusted = [save_CAM_list[0]]
    for i in range(1, len(save_CAM_list)):
        cur_x, cur_y = save_CAM_list[i]
        prev_x, prev_y = adjusted[-1]
        if cur_x == prev_x and cur_y != prev_y + 1:
            cur_y = prev_y + 1
        adjusted.append([cur_x, cur_y])
    return adjusted


def _is_image_capture_format(text) -> bool:
    """「画像取込XY」形式（画像取込+2桁のみ）に完全一致するか。画像取込01_はんだ等は該当せずtemplate2を使用"""
    if not isinstance(text, str):
        return False
    return re.fullmatch(r"画像取込\d{2}", text) is not None


def get_renamed_filenames(
    txt_path: str,
    filename_templates: dict | None = None,
) -> list[tuple[str, str]]:
    """
    txtファイルを読み込み、リネーム後の画像ファイル名一覧を返す
    
    Args:
        txt_path: txtファイルのパス
        filename_templates: ファイル名テンプレート（省略時はデフォルト）
    
    Returns:
        (元のファイル名, リネーム後のファイル名) のタプルのリスト
    """
    if filename_templates is None:
        filename_templates = {
            'template1': "{comment}_{index}",
            'template2': "{comment}_{tool}",
            'template3': "{original}",
        }
    
    folder_path = os.path.dirname(txt_path)
    log_path = os.path.join(os.path.dirname(folder_path), 'cammaster_seq.log')
    
    # txtファイルから情報を取得
    comment = ''
    file_list = []
    
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            if 'Comment=' in line:
                comment = line.replace('Comment=', '').strip()
            if 'FILE=' in line:
                fn = line.replace('FILE=', '').strip()
                if fn:
                    file_list.append(fn)
    
    # cammaster_seq.logからツールコメント取得（出現順のリスト＝撮像順に対応）
    cam_tool_comment_list = parse_cammaster_log_ordered(log_path)
    
    result = []
    used_names: set[str] = set()  # 重複回避用
    base_name_counts: dict[str, int] = {}  # 同じベース名の連番用（2番目以降は_2, _3...）
    
    for i, file_name in enumerate(file_list, 1):
        cam_div = _find_cam_and_div(file_name)
        cam = cam_div[0] if len(cam_div) > 0 else ''
        div = cam_div[1] if len(cam_div) > 1 else ''
        # ログのi番目（0-based: i-1）のエントリがこの画像に対応（複数回撮像の回数分）
        tool_comment = cam_tool_comment_list[i - 1] if i - 1 < len(cam_tool_comment_list) else None
        
        # テンプレート選択
        if comment:
            if _is_image_capture_format(tool_comment):
                template = filename_templates.get('template1', "{comment}_{index}")
            else:
                template = filename_templates.get('template2', "{comment}_{tool}")
        else:
            template = filename_templates.get('template3', "{original}")
        
        new_name = apply_filename_template(
            template=template,
            comment=comment,
            tool_comment=tool_comment,
            original_name=file_name.replace('.bmp', ''),
            cam=cam,
            div=div,
            index=i,
        )
        new_filename = f"{new_name}.bmp"
        base_name = new_name  # 重複時の連番付与用のベース名
        
        # 重複時は連番を付与（拡張_画像取込01_はんだ → 拡張_画像取込01_はんだ_2, _3, ...）
        while new_filename in used_names:
            count = base_name_counts.get(base_name, 2)
            while f"{base_name}_{count}.bmp" in used_names:
                count += 1
            new_name = f"{base_name}_{count}"
            new_filename = f"{new_name}.bmp"
            base_name_counts[base_name] = count + 1
        base_name_counts[base_name] = 2  # 次回重複時は_2から
        used_names.add(new_filename)
        
        result.append((file_name, new_filename))
    
    return result


class TestExtractImageFilenames(unittest.TestCase):
    """画像ファイル名抽出のテストクラス"""
    
    def setUp(self):
        """テスト用の一時txtファイルを作成"""
        self.test_dir = os.path.dirname(os.path.abspath(__file__))
        self.sample_txt_path = os.path.join(self.test_dir, 'test_sample.txt')
        
        # サンプルtxtファイルの内容（実際のVTVタスク形式）
        sample_content = """Comment=検査画像サンプル
Locked=1
FILE=1_1_001.bmp
FILE=1_2_002.bmp
FILE=2_1_003.bmp
"""
        with open(self.sample_txt_path, 'w', encoding='utf-8') as f:
            f.write(sample_content)
    
    def tearDown(self):
        """テスト用ファイルを削除"""
        if os.path.exists(self.sample_txt_path):
            os.remove(self.sample_txt_path)
    
    def test_extract_image_filenames(self):
        """FILE=行から画像ファイル名が正しく抽出されるか"""
        result = extract_image_filenames_from_txt(self.sample_txt_path)
        expected = ['1_1_001.bmp', '1_2_002.bmp', '2_1_003.bmp']
        self.assertEqual(result, expected)
    
    def test_extract_empty_file(self):
        """FILE=行がない場合は空リストを返すか"""
        empty_txt = os.path.join(self.test_dir, 'test_empty.txt')
        with open(empty_txt, 'w', encoding='utf-8') as f:
            f.write("Comment=コメントのみ\nLocked=0\n")
        try:
            result = extract_image_filenames_from_txt(empty_txt)
            self.assertEqual(result, [])
        finally:
            if os.path.exists(empty_txt):
                os.remove(empty_txt)
    
    def test_extract_nonexistent_file(self):
        """存在しないファイルの場合は空リストを返すか"""
        result = extract_image_filenames_from_txt(os.path.join(self.test_dir, 'nonexistent.txt'))
        self.assertEqual(result, [])


def main():
    """テスト実行、または指定ファイルの画像一覧表示"""
    # コマンドライン引数でファイルパスが指定された場合
    if len(sys.argv) >= 2:
        txt_path = sys.argv[1].strip('"').strip("'")
        print("=" * 60)
        print(f"指定ファイル: {txt_path}")
        print("=" * 60)
        
        if not os.path.exists(txt_path):
            print("\n[エラー] ファイルが存在しません。")
            print("パスを確認してください。")
            return 1
        
        filenames = extract_image_filenames_from_txt(txt_path)
        print("\n【抽出した画像ファイル一覧（元のファイル名）】")
        print("-" * 50)
        if filenames:
            for i, name in enumerate(filenames, 1):
                print(f"  {i}. {name}")
            print(f"\n合計: {len(filenames)} 件の画像ファイル")
        else:
            print("  (FILE= 行がありません)")
        
        # リネーム後の一覧を表示
        print("\n【リネーム後の画像ファイル一覧】")
        print("-" * 50)
        try:
            renamed_list = get_renamed_filenames(txt_path)
            if renamed_list:
                for i, (orig, new_name) in enumerate(renamed_list, 1):
                    print(f"  {i}. {orig}  →  {new_name}")
                print(f"\n合計: {len(renamed_list)} 件")
            else:
                print("  (リネーム対象がありません)")
        except Exception as e:
            print(f"  [エラー] リネーム一覧の取得に失敗しました: {e}")
        
        print("=" * 60)
        return 0
    
    # 引数なしの場合はユニットテストのみ実行
    print("=" * 60)
    print("txtファイルから画像ファイル名一覧を抽出するテスト")
    print("=" * 60)
    
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestExtractImageFilenames)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n※ 実際のファイルで試す場合:")
    print('  python test_read_txt_image_list.py "C:\\path\\to\\your\\file.txt"')
    print("=" * 60)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    exit(main())
