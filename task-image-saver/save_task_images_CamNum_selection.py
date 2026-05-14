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
    invalid_chars = r'[\\/:*?"<>|]'
    sanitized = re.sub(invalid_chars, '_', str(filename))
    sanitized = sanitized.strip(' .')
    if not sanitized:
        sanitized = 'unnamed'
    return sanitized


def apply_filename_template(template, comment, tool_comment, original_name,
                            cam, div, index, file_source=None):
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
        file_source: 参照元テキストファイル名（拡張子なし）

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
        "file": "" if file_source is None else str(file_source),
    }

    pattern = re.compile(r"\{([a-zA-Z0-9_]+)(?::([^{}]+))?\}")

    def _replace(match):
        name = match.group(1)
        fmt = match.group(2)

        if name not in values:
            return ""

        raw = values.get(name, "")
        if fmt:
            try:
                as_int = int(raw) if str(raw).strip() != "" else 0
                return format(as_int, fmt)
            except Exception:
                try:
                    return format(raw, fmt)
                except Exception:
                    return str(raw)

        return str(raw)

    result = pattern.sub(_replace, str(template) if template is not None else "")
    return sanitize_filename(result)


# ---------------------------------------------------------------------------
# 共通ヘルパー関数（旧 get_camera_list / process_images 内の重複を排除）
# ---------------------------------------------------------------------------

def get_file_list(folder_path, extension='.txt'):
    """指定フォルダから指定拡張子のファイルリストを取得"""
    extension = extension.lower()
    return [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(extension)
    ]


def find_cam_and_div(filename):
    """ファイル名からカメラ番号とDIV番号を抽出"""
    numbers = re.findall(r'\d+', filename)
    return [int(num) for num in numbers[:2]]


def adjust_save_CAM_list(save_CAM_list):
    """カラー画像のDIV番号を連番に修正"""
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
    """最初のテキストファイルを処理してカメラ・DIVリストを取得"""
    save_CAM_list = []
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            if '.DIV' in line:
                save_CAM_list.append(find_cam_and_div(line))
    return save_CAM_list


def is_image_capture_format(text):
    """「画像取込XX」形式（画像取込+2桁のみ）に完全一致するか判定"""
    if not isinstance(text, str):
        return False
    return re.fullmatch(r"画像取込\d{2}", text) is not None


def should_save_file(save_mode, img_info_dict):
    """画像ファイルを保存するかどうかを判定"""
    if save_mode == '0':
        return True
    if (save_mode == '1'
            and img_info_dict.get('comment')
            and img_info_dict['comment'] != 'この画像は自動で保存されました。'):
        return True
    if save_mode == '2' and img_info_dict.get('lockMode') == '1':
        return True
    return False


def create_mapping(original_list, converted_list):
    """2つのリスト間の双方向マッピングを作成"""
    mapping_AB = {}
    mapping_BA = {}
    for original, converted in zip(original_list, converted_list):
        mapping_AB[tuple(converted)] = tuple(original)
        mapping_BA[tuple(original)] = tuple(converted)
    return mapping_AB, mapping_BA


def get_original_from_converted(converted_element, mapping_AB):
    """変換後の要素から変換前の要素を取得"""
    return mapping_AB.get(tuple(converted_element), None)


def get_converted_from_original(original_element, mapping_BA):
    """変換前の要素から変換後の要素を取得"""
    return mapping_BA.get(tuple(original_element), None)


def is_element_in_2d_array(target, array_2d):
    """2D配列内に特定の要素が含まれるかチェック"""
    return any(target == element for element in array_2d)


def generate_new_file_name(img_info_dict, file_name, index, tool_comment,
                           cam, div, filename_templates,
                           is_duplicate_comment=False):
    """テンプレートを使用してファイル名を生成"""
    comment = img_info_dict.get('comment', '')
    original_name = os.path.splitext(file_name)[0]
    file_source = img_info_dict.get('fileName', '')

    if comment:
        if is_image_capture_format(tool_comment):
            template = filename_templates.get('template1', "{comment}_{index}")
        else:
            template = filename_templates.get('template2', "{comment}_{tool}")
    else:
        template = filename_templates.get('template3', "{original}")

    if is_duplicate_comment and comment:
        template = template + "_{file}"

    return apply_filename_template(
        template=template,
        comment=comment,
        tool_comment=tool_comment,
        original_name=original_name,
        cam=cam,
        div=div,
        index=index,
        file_source=file_source,
    )


def copy_image_files(img_info_dict, output_folder, folder_path,
                     cam_tool_comment_list, filename_templates,
                     is_duplicate_comment=False,
                     camera_filter=None, mapping_BA=None):
    """
    画像ファイルをコピーする統合関数。

    camera_filter が None の場合は全ファイルをコピー。
    camera_filter が指定されている場合は該当カメラのファイルのみコピー。
    """
    used_in_session = set()
    base_name_counts = {}

    for i, (file_name, log_idx) in enumerate(img_info_dict['fileNameList'], 1):
        cam_div = find_cam_and_div(file_name)
        cam = cam_div[0] if len(cam_div) > 0 else ''
        div = cam_div[1] if len(cam_div) > 1 else ''
        tool_comment = (cam_tool_comment_list[log_idx]
                        if log_idx < len(cam_tool_comment_list) else None)

        if camera_filter is not None and mapping_BA is not None:
            converted = get_converted_from_original(cam_div, mapping_BA)
            if converted is None or not is_element_in_2d_array(list(converted), camera_filter):
                continue

        new_file_name = generate_new_file_name(
            img_info_dict, file_name, i, tool_comment, cam, div,
            filename_templates, is_duplicate_comment,
        )
        base_name = new_file_name
        new_filename = f"{new_file_name}.bmp"

        while (new_filename in used_in_session
               or os.path.exists(os.path.join(output_folder, new_filename))):
            count = base_name_counts.get(base_name, 2)
            while (f"{base_name}_{count}.bmp" in used_in_session
                   or os.path.exists(os.path.join(output_folder,
                                                  f"{base_name}_{count}.bmp"))):
                count += 1
            new_file_name = f"{base_name}_{count}"
            new_filename = f"{new_file_name}.bmp"
            base_name_counts[base_name] = count + 1

        base_name_counts[base_name] = 2
        used_in_session.add(new_filename)
        shutil.copy(
            os.path.join(folder_path, file_name),
            os.path.join(output_folder, new_filename),
        )


def copy_raw_bmp_files(folder_path, output_folder, progress_callback=None,
                       cancel_check=None):
    """参照用txtがない場合に、imgフォルダ直下のBMPをそのままコピーする。"""
    bmp_files = get_file_list(folder_path, '.bmp')
    used_in_session = set()
    os.makedirs(output_folder, exist_ok=True)

    for i, file_name in enumerate(bmp_files, 1):
        if cancel_check and cancel_check():
            if progress_callback:
                progress_callback(i - 1, len(bmp_files), "キャンセルされました")
            return

        base_name, ext = os.path.splitext(file_name)
        new_filename = file_name
        count = 2
        while (new_filename in used_in_session
               or os.path.exists(os.path.join(output_folder, new_filename))):
            new_filename = f"{base_name}_{count}{ext}"
            count += 1

        used_in_session.add(new_filename)
        shutil.copy(
            os.path.join(folder_path, file_name),
            os.path.join(output_folder, new_filename),
        )

        if progress_callback:
            progress_callback(i, len(bmp_files), f"保存中: {file_name}")


# ---------------------------------------------------------------------------
# メイン公開関数
# ---------------------------------------------------------------------------

def get_camera_list(folder_path):
    """imgフォルダからカメラリスト(調整済み)を取得する関数"""
    file_list = get_file_list(folder_path)
    if not file_list:
        return []
    first_file = file_list[0]
    file_path = os.path.join(folder_path, first_file)
    save_CAM_list = process_first_file(file_path)
    return adjust_save_CAM_list(save_CAM_list)


def parse_cammaster_log(log_file_path):
    """cammaster_seq.logからカメラ情報を辞書形式で取得"""
    cam_info_dict = {}
    with open(log_file_path, 'r', encoding='utf-8') as file:
        print("read cammaster_seq.log")
        for line in file:
            match = re.search(
                r'\((\d+),\s*(\d+):\d+\)\s*:\s*画像取込,\s*name\s*=\s*(\w+)', line)
            if match:
                x = int(match.group(1))
                y = int(match.group(2))
                zzz = match.group(3)
                cam_info_dict[(x, y)] = zzz
    return cam_info_dict


def parse_cammaster_log_ordered(log_file_path):
    """cammaster_seq.logを読み込み、出現順にツール名のリストを返す"""
    result = []
    if not os.path.exists(log_file_path):
        return result
    with open(log_file_path, 'r', encoding='utf-8') as file:
        for line in file:
            match = re.search(
                r'\((\d+),\s*(\d+):\d+\)\s*:\s*画像取込,\s*name\s*=\s*(\w+)', line)
            if match:
                result.append(match.group(3))
    return result


def process_images(folder_path, output_folder, save_mode, save_cam,
                   output_file_path=None, preselected_cam_list=None,
                   progress_callback=None, filename_templates=None,
                   cancel_check=None):
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
    if filename_templates is None:
        filename_templates = {
            'template1': "{comment}_{index}",
            'template2': "{comment}_{tool}",
            'template3': "{original}",
        }

    log_file_path = os.path.join(os.path.dirname(folder_path), 'cammaster_seq.log')
    cam_tool_comment_list = parse_cammaster_log_ordered(log_file_path)
    file_index = [0]
    seen_comments = {}

    def process_file(file_path, img_info_dict, file_name_list):
        """各テキストファイルの内容を処理して画像情報を収集"""
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if 'Comment=' in line:
                    img_info_dict['comment'] = line.replace('Comment=', '').strip()
                if 'Locked=' in line:
                    img_info_dict['lockMode'] = line.replace('Locked=', '').strip()
                if 'FILE=' in line:
                    file_name = line.replace('FILE=', '').strip()
                    idx = file_index[0]
                    file_index[0] += 1
                    if should_save_file(save_mode, img_info_dict):
                        file_name_list.append((file_name, idx))

    file_list = get_file_list(folder_path)
    first_file = file_list[0] if file_list else None
    save_CAM_list = []
    mapping_BA = {}

    total_files = len(file_list)
    processed_count = 0

    if not file_list:
        if save_mode == '0':
            copy_raw_bmp_files(
                folder_path, output_folder,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
        elif progress_callback:
            progress_callback(0, 0, "参照用txtがないため保存対象がありません")
        return

    for filename in file_list:
        if cancel_check and cancel_check():
            print("画像処理がキャンセルされました")
            if progress_callback:
                progress_callback(processed_count, total_files, "キャンセルされました")
            return

        if progress_callback:
            progress_callback(processed_count, total_files, f"処理中: {filename}")

        file_path = os.path.join(folder_path, filename)
        img_info_dict = {'fileName': os.path.splitext(filename)[0]}
        file_name_list = []
        file_index[0] = 0

        if filename == first_file:
            raw_cam_list = process_first_file(file_path)
            print("save_CAM_list=")
            print(raw_cam_list)
            adjust_CAM_list = adjust_save_CAM_list(raw_cam_list)
            print("adjust_CAM_list=")
            print(adjust_CAM_list)
            mapping_AB, mapping_BA = create_mapping(raw_cam_list, adjust_CAM_list)
            sample_mapping = get_original_from_converted([1, 1], mapping_AB)
            if sample_mapping is not None:
                print(f"変換要素：{list(sample_mapping)}")

        if filename == first_file and save_cam == '1':
            if preselected_cam_list is not None:
                save_CAM_list = preselected_cam_list
            else:
                save_CAM_list = adjust_CAM_list

        process_file(file_path, img_info_dict, file_name_list)
        img_info_dict['fileNameList'] = file_name_list

        comment = img_info_dict.get('comment', '')
        current_source = img_info_dict.get('fileName', '')
        is_duplicate_comment = False
        if comment:
            if comment in seen_comments and seen_comments[comment] != current_source:
                is_duplicate_comment = True
                print(f"重複コメント検出: '{comment}' "
                      f"(初出: {seen_comments[comment]}, 今回: {current_source})")
            elif comment not in seen_comments:
                seen_comments[comment] = current_source

        if save_cam == '0':
            copy_image_files(
                img_info_dict, output_folder, folder_path,
                cam_tool_comment_list, filename_templates, is_duplicate_comment,
            )
        elif save_cam == '1':
            copy_image_files(
                img_info_dict, output_folder, folder_path,
                cam_tool_comment_list, filename_templates, is_duplicate_comment,
                camera_filter=save_CAM_list, mapping_BA=mapping_BA,
            )

        processed_count += 1
        if progress_callback:
            progress_callback(processed_count, total_files, f"完了: {filename}")

    if progress_callback:
        progress_callback(total_files, total_files, "処理完了")


if __name__ == "__main__":
    if len(sys.argv) > 4:
        folder_path = sys.argv[1]
        output_folder = sys.argv[2]
        save_mode = sys.argv[3]
        save_cam = sys.argv[4]
        process_images(folder_path, output_folder, save_mode, save_cam)
    else:
        print("引数が足りません。")
