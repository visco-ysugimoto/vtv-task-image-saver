# -*- mode: python ; coding: utf-8 -*-
"""
FletアプリケーションをWindowsのexeにビルドするためのspecファイル
Flet 0.80+ 対応版 (軽量化版)
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

# 追加のhidden imports（Flet関連）— 必要最小限に絞る
hidden_imports = collect_submodules('flet') + [
    'PIL',
    'PIL.Image',
    'PIL.JpegImagePlugin',
    'PIL.BmpImagePlugin',
    'PIL.PngImagePlugin',
    'tkinter',
    'tkinter.filedialog',
]

# flet_desktopのサブモジュールを追加（存在する場合）
try:
    hidden_imports += collect_submodules('flet_desktop') + ['flet_desktop']
except Exception:
    pass

# 不要モジュールの除外リスト
excludes = [
    'numpy',
    'scipy',
    'pandas',
    'matplotlib',
    'PIL.AvifImagePlugin',
    'PIL.WebPImagePlugin',
    'PIL.ImageCms',
    'PIL.SpiderImagePlugin',
    'PIL.FitsImagePlugin',
    'PIL.Hdf5StubImagePlugin',
    'PIL.MicImagePlugin',
    'flet.testing',
    'test',
    'unittest',
    'pydoc',
    'doctest',
    'lib2to3',
]

a = Analysis(
    ['main_save_task_images_flet.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('共有VTVフォルダパス.sample.json', '.'),
        ('icon_image.png', '.'),
        ('icon_image.ico', '.'),
    ] + flet_datas + flet_desktop_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# --- 軽量化: 不要なバイナリ/データを除外 ---
import fnmatch

_exclude_binaries = [
    '*avif*',
    '*webp*',
    '*imagecms*',
    '*openjp2*',
]

a.binaries = [
    b for b in a.binaries
    if not any(fnmatch.fnmatch(b[0].lower(), pat) for pat in _exclude_binaries)
]

_exclude_datas = [
    '*/tzdata/*',
]

a.datas = [
    d for d in a.datas
    if not any(fnmatch.fnmatch(d[0].lower(), pat) for pat in _exclude_datas)
]

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
    icon='icon_image.ico',  # アイコンファイル（icon_image.png から変換）
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
