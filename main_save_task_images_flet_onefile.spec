# -*- mode: python ; coding: utf-8 -*-
"""
FletアプリケーションをWindowsの単一exeにビルドするためのspecファイル
（1つのexeファイルに全てをまとめるバージョン）

注意: ファイルサイズが大きくなり、起動が少し遅くなります。
      配布の簡便さを重視する場合に使用してください。
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Fletの必要なデータファイルを収集
flet_datas = collect_data_files('flet')
flet_desktop_datas = collect_data_files('flet_desktop')

# Pillowのデータファイル
pillow_datas = collect_data_files('PIL')

# 追加のhidden imports（Flet関連）
hidden_imports = collect_submodules('flet') + collect_submodules('flet_desktop') + [
    'flet_desktop',
    'PIL',
    'PIL.Image',
    'tkinter',
    'tkinter.filedialog',
]

a = Analysis(
    ['main_save_task_images_flet.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('共有VTVフォルダパス.sample.json', '.'),
        ('icon_image.png', '.'),
        ('save_task_images.ico', '.'),
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

# 単一ファイル版 (onefile)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TaskImageSaver',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUIアプリなのでコンソール非表示
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='save_task_images.ico',
)
