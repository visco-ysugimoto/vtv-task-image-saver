# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main_save_task_images_flet.py'],
    pathex=[],
    binaries=[],
    datas=[('icon_image.png', '.'), ('save_task_images.ico', '.'), ('..\\.venv\\Lib\\site-packages\\flet\\controls\\material\\icons.json', 'flet\\controls\\material')],
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
    [],
    exclude_binaries=True,
    name='TaskImageSaver',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:\\Users\\YSUGIM~1.VIS\\AppData\\Local\\Temp\\0411954e-c59d-4473-b6e8-7d3d11f0332a',
    icon=['save_task_images.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TaskImageSaver',
)
