TaskImageSaver（タスク画像保存フロー）
=====================================

## 動作環境

- Windows 10 / 11（64bit）
- Python のインストールは不要です
- インストール先のフォルダ名に日本語を含めても構いません

## 配布 ZIP の整合性確認（任意）

配布元から `TaskImageSaver_v*_win64.zip` と
`TaskImageSaver_v*_win64.zip.sha256` の両方を受け取った場合、
PowerShell で次のように照合できます。

  Get-FileHash .\TaskImageSaver_v*_win64.zip -Algorithm SHA256

表示された Hash が .sha256 ファイルの先頭の英数字列と一致することを確認してください。

## 使い方

1. このフォルダごと任意の場所にコピーしてください
2. TaskImageSaver.exe をダブルクリックして起動します
   （日本語パスでは初回のみ app フォルダを内部同期します。同一ドライブでは
     実体コピーなしの高速リンクを使います。設定はこのフォルダを参照します）
3. タスクファイル (.ziq 等) はウィンドウへドラッグ＆ドロップできます

## 共有 VTV フォルダ設定（Option3 を使う場合）

1. 「共有VTVフォルダパス.sample.json」をコピーし、
   「共有VTVフォルダパス.json」にリネームします
2. option3_folder に共有フォルダのパスを記入して保存します

※ 設定ファイルはこのフォルダ（インストール先）に置いてください。

## 右クリックメニュー（任意）

.ziq 等を右クリックからプレビュー起動したい場合:

  register_task_image_saver_context_menu.cmd を実行

解除:

  unregister_task_image_saver_context_menu.cmd を実行

※ 管理者権限は不要です（現在のユーザー設定のみ変更します）
※ メニューは TaskImageSaver.exe（ランチャー）を登録します

## トラブルシューティング

### 起動直後に終了する

1. **フォルダごと**展開・コピーしているか確認
   （TaskImageSaver.exe だけ移動しない。app フォルダ内の本体・DLL 群が必要です）
2. ZIP を右クリック → **プロパティ** → **ブロックの解除**（表示される場合）
3. 次を削除してから再起動:
   - `%AppData%\Roaming\VISCO\TaskImageSaver`
   - `%LOCALAPPDATA%\VISCO\TaskImageSaver\runtime`（存在する場合）
4. TaskImageSaver_debug.cmd でログを確認

### ログの場所

  %LOCALAPPDATA%\VISCO\TaskImageSaver\console.log
  （インストールフォルダの startup.log も参照）

### ドラッグ＆ドロップだけ動かない

環境変数 TASK_IMAGE_SAVER_NO_DROPZONE=1 で D&D を無効化できます（診断用）。

## 同梱ファイル

- TaskImageSaver.exe … 起動用ランチャー（こちらを実行）
- app\TaskImageSaverApp.exe … アプリ本体（直接起動しない）
- app\...（DLL / data / Lib など）… 本体実行に必要
- 共有VTVフォルダパス.sample.json … 設定ファイルのサンプル
- register / unregister … 右クリックメニュー登録用
