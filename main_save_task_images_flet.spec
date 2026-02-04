# -*- mode: python ; coding: utf-8 -*-
"""
FletアプリケーションをWindowsのexeにビルドするためのspecファイル
Flet 0.80+ 対応版
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Fletの必要なデータファイルを収集
flet_datas = collect_data_files('flet')

# flet_desktopが存在する場合のみ収集（Flet 0.80+では統合されている可能性）
try:
    flet_desktop_datas = collect_data_files('flet_desktop')
except Exception:
    flet_desktop_datas = []

# Pillowのデータファイル
pillow_datas = collect_data_files('PIL')

# 追加のhidden imports（Flet関連）
hidden_imports = collect_submodules('flet') + [
    'PIL',
    'PIL.Image',
    'tkinter',
    'tkinter.filedialog',
]

# flet_desktopのサブモジュールを追加（存在する場合）
try:
    hidden_imports += collect_submodules('flet_desktop') + ['flet_desktop']
except Exception:
    pass

a = Analysis(
    ['main_save_task_images_flet.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('共有VTVフォルダパス.sample.json', '.'),  # サンプル設定ファイル
        ('icon_image.png', '.'),  # アイコン画像
        ('save_task_images.ico', '.'),  # 実行時参照用（window.icon用）
    ] + flet_datas + flet_desktop_datas + pillow_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TaskImageSaver',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUIアプリなのでコンソール非表示
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='save_task_images.ico',  # アイコンファイル（.ico形式）
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TaskImageSaver',
)
