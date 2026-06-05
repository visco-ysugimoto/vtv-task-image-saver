# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: 配布用 TaskImageSaver.exe ランチャー（Flet 非同梱）

import os

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_ROOT = os.path.normpath(os.path.join(SPEC_DIR, ".."))
APP_DIR = os.path.join(PROJECT_ROOT, "app")
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "launcher.ico")

a = Analysis(
    [os.path.join(SPEC_DIR, "task_image_saver_launcher.py")],
    pathex=[APP_DIR],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TaskImageSaver",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
)
