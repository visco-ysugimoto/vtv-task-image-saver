import sys
import os
import shutil
import re
import dynamic_gui_CamNum_selection

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
def process_images(folder_path, output_folder, save_mode, save_cam, output_file_path=None):
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
            print(cam_tool_comment_dict.get(get_converted_from_original(find_cam_and_div(file_name),mapping_BA)))
            tool_comment = cam_tool_comment_dict.get(get_converted_from_original(find_cam_and_div(file_name),mapping_BA))
            print(f"tool_comment={tool_comment}")
            if is_image_capture_format(tool_comment):
                new_file_name = generate_new_file_name(img_info_dict, file_name,i)
            else:
                new_file_name = generate_new_file_name(img_info_dict, file_name,tool_comment)
            original_file_name = file_name.replace(".bmp", "")  # 元のファイル名を取得
            print(f"newfilename={new_file_name}")
            while os.path.exists(os.path.join(output_folder, f"{new_file_name}.bmp")):
                new_file_name = f"{new_file_name}_{original_file_name}"
            shutil.copy(os.path.join(folder_path, file_name), os.path.join(output_folder, f"{new_file_name}.bmp"))

    # 特定のカメラ番号のファイルを選んでコピー
    def copy_select_files(img_info_dict, output_folder, folder_path, adjust_CAM_list, mapping_BA,save_CAM_list):
        for i, file_name in enumerate(img_info_dict['fileNameList'], 1):
            print("test")
            print(find_cam_and_div(file_name))
            if is_element_in_2d_array(list(get_converted_from_original(find_cam_and_div(file_name),mapping_BA)), save_CAM_list):  # 指定されたカメラ番号に一致するか確認
                print(cam_tool_comment_dict.get(get_converted_from_original(find_cam_and_div(file_name),mapping_BA)))
                tool_comment = cam_tool_comment_dict.get(get_converted_from_original(find_cam_and_div(file_name),mapping_BA))
                if is_image_capture_format(tool_comment):
                    new_file_name = generate_new_file_name(img_info_dict, file_name,i)
                else:
                    new_file_name = generate_new_file_name(img_info_dict, file_name,tool_comment)
                original_file_name = file_name.replace(".bmp", "")  # 元のファイル名を取得
                while os.path.exists(os.path.join(output_folder, f"{new_file_name}.bmp")):
                    new_file_name = f"{new_file_name}_{original_file_name}"
                shutil.copy(os.path.join(folder_path, file_name), os.path.join(output_folder, f"{new_file_name}.bmp"))

    # 新しいファイル名を生成
    def generate_new_file_name(img_info_dict, file_name, index):
        if img_info_dict.get('comment'):
            return f"{img_info_dict['comment']}_{index}" if len(img_info_dict['fileNameList']) >= 1 else img_info_dict['comment']   # 撮像回数が1回以上でツールコメントを付ける
        return file_name.replace(".bmp", '')

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

    # 各ファイルを処理
    for filename in file_list:
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
            save_CAM_list = dynamic_gui_CamNum_selection.create_gui(adjust_CAM_list)

        process_file(file_path, img_info_dict, file_name_list)
        img_info_dict['fileNameList'] = file_name_list

        if save_cam == '0':
            copy_files(img_info_dict, output_folder, folder_path)
        elif save_cam == '1':
            copy_select_files(img_info_dict, output_folder, folder_path, adjust_CAM_list, mapping_BA,save_CAM_list)

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
