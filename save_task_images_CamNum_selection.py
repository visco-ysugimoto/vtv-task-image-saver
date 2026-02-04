import sys
import os
import shutil
import re


def sanitize_filename(filename):
    """
    Windowsで使用できない文字をファイル名から除去・置換する関数
    
    Args:
        filename: サニタイズするファイル名
    
    Returns:
        無効な文字を除去したファイル名
    """
    # Windowsで使用できない文字: \ / : * ? " < > |
    invalid_chars = r'[\\/:*?"<>|]'
    # 無効な文字をアンダースコアに置換
    sanitized = re.sub(invalid_chars, '_', str(filename))
    # 先頭・末尾の空白とドットを除去（Windowsの制限）
    sanitized = sanitized.strip(' .')
    # 空文字列になった場合はデフォルト名を返す
    if not sanitized:
        sanitized = 'unnamed'
    return sanitized


def apply_filename_template(template, comment, tool_comment, original_name, cam, div, index):
    """
    テンプレートにプレースホルダーを適用してファイル名を生成する関数
    
    Args:
        template: ファイル名テンプレート（例: "{comment}_{index}"）
        comment: 画像コメント
        tool_comment: ツールコメント
        original_name: 元のファイル名（拡張子なし）
        cam: カメラ番号
        div: DIV番号（列番号）
        index: 連番
    
    Returns:
        プレースホルダーを置換したファイル名（サニタイズ済み）
    """
    values = {
        "comment": "" if comment is None else str(comment),
        "tool": "" if tool_comment is None else str(tool_comment),
        "original": "" if original_name is None else str(original_name),
        "cam": "" if cam is None else str(cam),
        "div": "" if div is None else str(div),
        "index": "" if index is None else str(index),
    }

    # {name} / {name:03} の簡易フォーマット指定に対応
    pattern = re.compile(r"\{([a-zA-Z0-9_]+)(?::([^{}]+))?\}")

    def _replace(match):
        name = match.group(1)
        fmt = match.group(2)

        if name not in values:
            # 未対応プレースホルダーは空文字にする（プレビュー/本処理の両方で安全に）
            return ""

        raw = values.get(name, "")
        if fmt:
            # 数値ゼロ埋め目的を想定し、まずint変換を試す
            try:
                as_int = int(raw) if str(raw).strip() != "" else 0
                return format(as_int, fmt)
            except Exception:
                # 文字列などはフォーマットに失敗する可能性があるためフォールバック
                try:
                    return format(raw, fmt)
                except Exception:
                    return str(raw)

        return str(raw)

    result = pattern.sub(_replace, str(template) if template is not None else "")
    return sanitize_filename(result)


def get_camera_list(folder_path):
    """
    imgフォルダからカメラリスト(調整済み)を取得する関数
    
    Args:
        folder_path: imgフォルダのパス
    
    Returns:
        カメラリストの2次元配列 例: [[1, 1], [1, 2], [2, 1], [2, 2]]
    """
    def get_file_list(folder_path, extension='.txt'):
        return [filename for filename in os.listdir(folder_path) if filename.endswith(extension)]

    def find_cam_and_div(filename):
        numbers = re.findall(r'\d+', filename)
        return [int(num) for num in numbers[:2]]

    def adjust_save_CAM_list(save_CAM_list):
        if not save_CAM_list:
            return save_CAM_list
        adjusted_list = [save_CAM_list[0]]
        for i in range(1, len(save_CAM_list)):
            current_X, current_Y = save_CAM_list[i]
            previous_X, previous_Y = adjusted_list[-1]
            if current_X == previous_X:
                if current_Y != previous_Y + 1:
                    current_Y = previous_Y + 1
            adjusted_list.append([current_X, current_Y])
        return adjusted_list

    def process_first_file(file_path):
        save_CAM_list = []
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if '.DIV' in line:
                    save_CAM_list.append(find_cam_and_div(line))
        return save_CAM_list

    file_list = get_file_list(folder_path)
    if not file_list:
        return []
    
    first_file = file_list[0]
    file_path = os.path.join(folder_path, first_file)
    save_CAM_list = process_first_file(file_path)
    adjust_CAM_list = adjust_save_CAM_list(save_CAM_list)
    
    return adjust_CAM_list


# 画像取込ツールのコメントを取得する関数:cammaster_seq.logから情報を抽出
def parse_cammaster_log(log_file_path):
    cam_info_dict = {}
    with open(log_file_path, 'r', encoding='utf-8') as file:
        print("read cammaster_seq.log")
        for line in file:
            match = re.search(r'\((\d+),\s*(\d+):\d+\)\s*:\s*画像取込,\s*name\s*=\s*(\w+)', line)
            if match:
                x = int(match.group(1))
                y = int(match.group(2))
                zzz = match.group(3)
                cam_info_dict[(x, y)] = zzz
    return cam_info_dict

# 画像を処理するためのメイン関数
def process_images(folder_path, output_folder, save_mode, save_cam, output_file_path=None, preselected_cam_list=None, progress_callback=None, filename_templates=None, cancel_check=None):
    """
    画像を処理してコピーするメイン関数
    
    Args:
        progress_callback: 進捗を報告するコールバック関数 (current, total, message) -> None
        filename_templates: ファイル名テンプレートの辞書
            - template1: コメントあり + 画像取込XX形式
            - template2: コメントあり + その他
            - template3: コメントなし
        cancel_check: キャンセル状態をチェックするコールバック関数 () -> bool
    """
    # デフォルトのテンプレートを設定
    if filename_templates is None:
        filename_templates = {
            'template1': "{comment}_{index}",
            'template2': "{comment}_{tool}",
            'template3': "{original}",
        }
    # 追加: cammaster_seq.logの情報を取得
    log_file_path = os.path.join(os.path.dirname(folder_path), 'cammaster_seq.log')
    cam_tool_comment_dict = parse_cammaster_log(log_file_path)
    print("tool_comment=")
    print(cam_tool_comment_dict)
    
    # 指定された拡張子（デフォルトは.txt）のファイルリストを取得
    def get_file_list(folder_path, extension='.txt'):
        return [filename for filename in os.listdir(folder_path) if filename.endswith(extension)]

    # ファイル名からカメラ番号とDIV番号を抽出
    def find_cam_and_div(filename):
        numbers = re.findall(r'\d+', filename)
        return [int(num) for num in numbers[:2]]
    
    # カラー画像の時にDIVを修正するため使用
    def adjust_save_CAM_list(save_CAM_list):
    # リストが空でないことを確認
        if not save_CAM_list:
            return save_CAM_list

        # 1つ目の要素からスタート
        adjusted_list = [save_CAM_list[0]]

        for i in range(1, len(save_CAM_list)):
            current_X, current_Y = save_CAM_list[i]
            previous_X, previous_Y = adjusted_list[-1]  # 調整後のリストの最後の要素

            if current_X == previous_X:  # X_i = X_(i+1) の場合
                if current_Y != previous_Y + 1:  # Y_(i+1) と Y_i の差が1でない場合
                    current_Y = previous_Y + 1  # Y_(i+1) を Y_i + 1 に調整
            # 調整後の値をリストに追加
            adjusted_list.append([current_X, current_Y])
        return adjusted_list
    
    # 最初のファイルを処理して保存すべきカメラ番号をリストアップ
    def process_first_file(file_path):
        save_CAM_list = []
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if '.DIV' in line:  # DIVが含まれる行を処理
                    save_CAM_list.append(find_cam_and_div(line))
        return save_CAM_list

    # 各ファイルの内容を処理して画像情報を収集
    def process_file(file_path, img_info_dict, file_name_list):
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if 'Comment=' in line:  # コメント行を抽出
                    img_info_dict['comment'] = line.replace('Comment=', '').strip()
                if 'Locked=' in line:  # ロック状態を抽出
                    img_info_dict['lockMode'] = line.replace('Locked=', '').strip()
                if 'FILE=' in line:  # 画像ファイル名を抽出
                    file_name = line.replace('FILE=', '').strip()
                    if should_save_file(img_info_dict, file_name):  # 保存条件を満たすか確認
                        file_name_list.append(file_name)

    # 画像ファイルを保存するかどうかを判定
    def should_save_file(img_info_dict, file_name):
        if save_mode == '0':  # 全てのファイルを保存
            return True
        if save_mode == '1' and img_info_dict.get('comment') and img_info_dict['comment'] != 'この画像は自動で保存されました。':
            return True  # コメントがあり、指定のコメントでない場合に保存
        if save_mode == '2' and img_info_dict.get('lockMode') == '1':
            return True  # ロックされている画像のみ保存
        return False

    def is_image_capture_format(text):
        """
        入力された文字列が「画像取込XY」の形式に一致するかどうかを判定します。
        """
        if not isinstance(text, str):
            return False  # 文字列でない場合はFalseを返す
        # 正規表現パターン
        pattern = r"画像取込\d{2}"
        # 一致するかどうかを確認
        match = re.fullmatch(pattern, text)
        
        return match is not None

    # ファイルを指定フォルダにコピー
    def copy_files(img_info_dict, output_folder, folder_path):
        for i, file_name in enumerate(img_info_dict['fileNameList'], 1):
            # カメラ番号とDIV番号を取得
            cam_div = find_cam_and_div(file_name)
            cam = cam_div[0] if len(cam_div) > 0 else ''
            div = cam_div[1] if len(cam_div) > 1 else ''
            
            print(cam_tool_comment_dict.get(get_converted_from_original(cam_div, mapping_BA)))
            tool_comment = cam_tool_comment_dict.get(get_converted_from_original(cam_div, mapping_BA))
            print(f"tool_comment={tool_comment}")
            
            # テンプレートを使用してファイル名を生成
            new_file_name = generate_new_file_name(img_info_dict, file_name, i, tool_comment, cam, div)
            original_file_name = file_name.replace(".bmp", "")  # 元のファイル名を取得
            print(f"newfilename={new_file_name}")
            while os.path.exists(os.path.join(output_folder, f"{new_file_name}.bmp")):
                new_file_name = f"{new_file_name}_{original_file_name}"
            shutil.copy(os.path.join(folder_path, file_name), os.path.join(output_folder, f"{new_file_name}.bmp"))

    # 特定のカメラ番号のファイルを選んでコピー
    def copy_select_files(img_info_dict, output_folder, folder_path, adjust_CAM_list, mapping_BA, save_CAM_list):
        for i, file_name in enumerate(img_info_dict['fileNameList'], 1):
            # カメラ番号とDIV番号を取得
            cam_div = find_cam_and_div(file_name)
            cam = cam_div[0] if len(cam_div) > 0 else ''
            div = cam_div[1] if len(cam_div) > 1 else ''
            
            print("test")
            print(cam_div)
            if is_element_in_2d_array(list(get_converted_from_original(cam_div, mapping_BA)), save_CAM_list):  # 指定されたカメラ番号に一致するか確認
                print(cam_tool_comment_dict.get(get_converted_from_original(cam_div, mapping_BA)))
                tool_comment = cam_tool_comment_dict.get(get_converted_from_original(cam_div, mapping_BA))
                
                # テンプレートを使用してファイル名を生成
                new_file_name = generate_new_file_name(img_info_dict, file_name, i, tool_comment, cam, div)
                original_file_name = file_name.replace(".bmp", "")  # 元のファイル名を取得
                while os.path.exists(os.path.join(output_folder, f"{new_file_name}.bmp")):
                    new_file_name = f"{new_file_name}_{original_file_name}"
                shutil.copy(os.path.join(folder_path, file_name), os.path.join(output_folder, f"{new_file_name}.bmp"))

    # 新しいファイル名を生成（テンプレート対応）
    def generate_new_file_name(img_info_dict, file_name, index, tool_comment, cam, div):
        """
        テンプレートを使用してファイル名を生成
        
        Args:
            img_info_dict: 画像情報の辞書（comment, fileNameListなど）
            file_name: 元のファイル名
            index: 連番
            tool_comment: ツールコメント
            cam: カメラ番号
            div: DIV番号
        """
        comment = img_info_dict.get('comment', '')
        original_name = file_name.replace(".bmp", '')
        
        # 条件に応じてテンプレートを選択
        if comment:
            if is_image_capture_format(tool_comment):
                # 条件1: コメントあり + 画像取込XX形式
                template = filename_templates.get('template1', "{comment}_{index}")
            else:
                # 条件2: コメントあり + その他のツールコメント
                template = filename_templates.get('template2', "{comment}_{tool}")
        else:
            # 条件3: コメントなし
            template = filename_templates.get('template3', "{original}")
        
        # テンプレートを適用
        return apply_filename_template(
            template=template,
            comment=comment,
            tool_comment=tool_comment,
            original_name=original_name,
            cam=cam,
            div=div,
            index=index
        )

    def create_mapping(original_list, converted_list):
        # converted_listの各要素に対応するoriginal_listの要素を記憶する辞書を作成
        mapping_AB = {}  # converted_list -> original_list のマッピング
        mapping_BA = {}  # original_list -> converted_list のマッピング
        
        for original, converted in zip(original_list, converted_list):
            mapping_AB[tuple(converted)] = tuple(original)
            mapping_BA[tuple(original)] = tuple(converted)
            
        return mapping_AB, mapping_BA

    def get_original_from_converted(converted_element, mapping_AB):
        # converted_listの要素からoriginal_listの要素を取得する
        return mapping_AB.get(tuple(converted_element), None)

    def get_converted_from_original(original_element, mapping_BA):
        # original_listの要素からconverted_listの要素を取得する
        return mapping_BA.get(tuple(original_element), None)
    
    # 2D配列内に特定の要素が含まれるかチェック
    def is_element_in_2d_array(target, array_2d):
        return any(target == element for element in array_2d)

    # ファイルリストを取得
    file_list = get_file_list(folder_path)
    first_file = file_list[0] if file_list else None
    save_CAM_list = []
    
    total_files = len(file_list)
    processed_count = 0

    # 各ファイルを処理
    for filename in file_list:
        # キャンセルチェック
        if cancel_check and cancel_check():
            print("画像処理がキャンセルされました")
            if progress_callback:
                progress_callback(processed_count, total_files, "キャンセルされました")
            return
        
        # 進捗を報告
        if progress_callback:
            progress_callback(processed_count, total_files, f"処理中: {filename}")
        file_path = os.path.join(folder_path, filename)
        img_info_dict = {'fileName': filename.replace('.txt', '')}
        file_name_list = []
        
        # 最初のファイルについて、ツールコメントを取得
        if filename == first_file:
            save_CAM_list = process_first_file(file_path)
            print("save_CAM_list=")
            print(save_CAM_list)
            adjust_CAM_list = adjust_save_CAM_list(save_CAM_list)
            print("adjust_CAM_list=")
            print(adjust_CAM_list)
            # 対応関係を作成
            mapping_AB, mapping_BA = create_mapping(save_CAM_list, adjust_CAM_list)
            print(f"変換要素：{list(get_original_from_converted([1,1],mapping_AB))}")
        
        if filename == first_file and save_cam == '1':  # 最初のファイルを処理し、カメラ番号を選択
            if preselected_cam_list is not None:
                # 事前に選択されたカメラリストを使用（Fletから呼ばれた場合）
                save_CAM_list = preselected_cam_list
            else:
                # カメラリストが渡されていない場合は全てのカメラを選択
                save_CAM_list = adjust_CAM_list

        process_file(file_path, img_info_dict, file_name_list)
        img_info_dict['fileNameList'] = file_name_list

        if save_cam == '0':
            copy_files(img_info_dict, output_folder, folder_path)
        elif save_cam == '1':
            copy_select_files(img_info_dict, output_folder, folder_path, adjust_CAM_list, mapping_BA,save_CAM_list)
        
        # 進捗を更新
        processed_count += 1
        if progress_callback:
            progress_callback(processed_count, total_files, f"完了: {filename}")
    
    # 処理完了を報告
    if progress_callback:
        progress_callback(total_files, total_files, "処理完了")

# 外部ファイルから呼び出された場合の処理
if __name__ == "__main__":
    if len(sys.argv) > 4:
        folder_path = sys.argv[1]
        output_folder = sys.argv[2]
        save_mode = sys.argv[3]
        save_cam = sys.argv[4]
        process_images(folder_path, output_folder, save_mode, save_cam)
    else:
        print("引数が足りません。")
