"""
Flet アプリ用のリソース解決・ダイアログ・Windows アイコン設定。
UI フレームワークに依存しないユーティリティ。
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from utils import TASK_FILE_DIALOG_TYPES

# Windows タスクバーで独自アイコンを表示するための AppUserModelID 設定
if sys.platform == "win32":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "viscotech.taskimagesaver.1.0"
    )


def resolve_resource_path(filename: str) -> str | None:
    """PyInstaller exe / flet build / 開発環境の両方でリソースファイルのパスを解決する"""
    candidates = []
    base_meipass = getattr(sys, "_MEIPASS", None)
    if base_meipass:
        candidates.append(os.path.join(base_meipass, filename))
    flet_assets = os.environ.get("FLET_ASSETS_DIR")
    if flet_assets:
        candidates.append(os.path.join(flet_assets, filename))
    exe_dir = os.path.dirname(sys.executable)
    candidates.append(os.path.join(exe_dir, "_internal", filename))
    candidates.append(os.path.join(exe_dir, filename))
    candidates.append(os.path.join(exe_dir, "data", "flutter_assets", "assets", filename))
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_script_dir)
    candidates.append(os.path.join(_script_dir, filename))
    candidates.append(os.path.join(_script_dir, "assets", filename))
    candidates.append(os.path.join(_project_root, "assets", filename))
    for p in candidates:
        if p and os.path.exists(p):
            return os.path.abspath(p)
    return None


def set_window_icon_win32(window_title: str, ico_path: str):
    """Win32 API でウィンドウのタイトルバー・タスクバーアイコンを直接設定する"""
    if sys.platform != "win32" or not ico_path:
        return

    user32 = ctypes.windll.user32

    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
    ]
    user32.SetClassLongPtrW.restype = ctypes.c_size_t
    user32.SetClassLongPtrW.argtypes = [
        wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t,
    ]
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
    ]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM,
    )

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1
    GCLP_HICON = -14
    GCLP_HICONSM = -34
    SM_CXSMICON = 49
    SM_CYSMICON = 50

    def _find_process_windows():
        pid = os.getpid()
        hwnds = []

        @WNDENUMPROC
        def cb(hwnd, _):
            wpid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value == pid and user32.IsWindowVisible(hwnd):
                hwnds.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        return hwnds

    def _apply_icon(hwnds, hicon_small, hicon_big):
        for hwnd in hwnds:
            if hicon_small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
                user32.SetClassLongPtrW(hwnd, GCLP_HICONSM, hicon_small)
            if hicon_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
                user32.SetClassLongPtrW(hwnd, GCLP_HICON, hicon_big)

    def apply():
        time.sleep(1.5)
        hwnds = _find_process_windows()
        if not hwnds:
            hwnd = user32.FindWindowW(None, window_title)
            if hwnd:
                hwnds = [hwnd]
        if not hwnds:
            print("Window not found for icon setting")
            return

        sm_cx = user32.GetSystemMetrics(SM_CXSMICON) or 16
        sm_cy = user32.GetSystemMetrics(SM_CYSMICON) or 16
        hicon_small = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, sm_cx, sm_cy, LR_LOADFROMFILE,
        )
        hicon_big = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, 48, 48, LR_LOADFROMFILE,
        )
        print(f"Icon handles: small={hicon_small} ({sm_cx}x{sm_cy}), big={hicon_big}")
        print(f"Target windows: {len(hwnds)}")

        _apply_icon(hwnds, hicon_small, hicon_big)

        for delay in (1.0, 2.0):
            time.sleep(delay)
            _apply_icon(hwnds, hicon_small, hicon_big)

    threading.Thread(target=apply, daemon=True).start()


def _is_packaged_runtime() -> bool:
    """flet build 同梱 exe から動作しているか（tkinter 不可の目安）。"""
    if sys.platform != "win32":
        return False
    exe = Path(sys.executable).resolve()
    if exe.suffix.lower() != ".exe":
        return False
    if exe.name.lower() in ("python.exe", "pythonw.exe", "flet.exe"):
        return False
    return (exe.parent / "flutter_windows.dll").is_file()


def _tkinter_available() -> bool:
    if _is_packaged_runtime():
        return False
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


def _powershell_exe() -> str:
    if sys.platform != "win32":
        return ""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidates = [
        shutil.which("powershell.exe"),
        os.path.join(
            system_root,
            "System32",
            "WindowsPowerShell",
            "v1.0",
            "powershell.exe",
        ),
        os.path.join(
            system_root,
            "Sysnative",
            "WindowsPowerShell",
            "v1.0",
            "powershell.exe",
        ),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return ""


def _run_powershell_dialog(script: str, *, env: dict[str, str] | None = None) -> str:
    """配布 exe 向け: PowerShell (STA) でダイアログを表示する（コンソール非表示）。"""
    ps_exe = _powershell_exe()
    if not ps_exe:
        return ""

    out_file = Path(tempfile.gettempdir()) / (
        f"tis_dialog_{os.getpid()}_{threading.get_ident()}.txt"
    )
    out_file.unlink(missing_ok=True)

    full_env = os.environ.copy()
    full_env["TIS_OUT_FILE"] = str(out_file)
    if env:
        full_env.update(env)

    creationflags = 0
    startupinfo = None
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    try:
        subprocess.run(
            [
                ps_exe,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-STA",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            env=full_env,
            timeout=3600,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if out_file.is_file():
        try:
            return out_file.read_text(encoding="utf-8-sig").strip()
        finally:
            out_file.unlink(missing_ok=True)
    return ""


# フォルダ: IFileOpenDialog（フォルダのみ）→ 失敗時のみ FolderBrowserDialog
_SELECT_FOLDER_PS = r"""
$path = ''
$owner = [IntPtr]::Zero
if ($env:TIS_OWNER_HWND) { $owner = [IntPtr]::new([int64]$env:TIS_OWNER_HWND) }
try {
    $clsid = [Guid]'DC1C5A9C-E88A-4CDE-A481-9E1A61FD0ED4'
    $t = [Type]::GetTypeFromCLSID($clsid)
    if ($t) {
        $dlg = [Activator]::CreateInstance($t)
        $opt = [uint32]0x20 -bor [uint32]0x40 -bor [uint32]0x800
        $flags = [System.Reflection.BindingFlags]'Public,Instance'
        $null = $t.InvokeMember('SetOptions', $flags, $null, $dlg, @($opt))
        $null = $t.InvokeMember('SetTitle', $flags, $null, $dlg, @($env:TIS_DIALOG_TITLE))
        $hr = $t.InvokeMember('Show', $flags, $null, $dlg, @($owner))
        if ($hr -eq 0) {
            $item = $t.InvokeMember('GetResult', $flags, $null, $dlg, $null)
            $path = $item.GetType().InvokeMember(
                'GetDisplayName', $flags, $null, $item, @(0x80058000)
            )
        }
    }
} catch {}
if (-not $path) {
    Add-Type -AssemblyName System.Windows.Forms
    $fbd = New-Object System.Windows.Forms.FolderBrowserDialog
    $fbd.Description = $env:TIS_DIALOG_TITLE
    $fbd.ShowNewFolderButton = $true
    if ($fbd.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $path = $fbd.SelectedPath
    }
}
if ($path -and $env:TIS_OUT_FILE) {
    [IO.File]::WriteAllText($env:TIS_OUT_FILE, $path, [Text.UTF8Encoding]::new($false))
}
"""

# ファイル: AutoUpgradeEnabled で Vista+ スタイル（補助フォームなし）
_SELECT_FILE_PS = r"""
Add-Type -AssemblyName System.Windows.Forms
$path = ''
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.AutoUpgradeEnabled = $true
$dlg.Title = $env:TIS_DIALOG_TITLE
$dlg.Filter = $env:TIS_FILE_FILTER
$dlg.CheckFileExists = $true
if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    $path = $dlg.FileName
}
if ($path -and $env:TIS_OUT_FILE) {
    [IO.File]::WriteAllText($env:TIS_OUT_FILE, $path, [Text.UTF8Encoding]::new($false))
}
"""


def _powershell_dialog_env(title: str) -> dict[str, str]:
    env = {"TIS_DIALOG_TITLE": title}
    owner = _owner_hwnd()
    if owner:
        env["TIS_OWNER_HWND"] = str(owner)
    return env


def _select_folder_powershell() -> str:
    return _run_powershell_dialog(
        _SELECT_FOLDER_PS,
        env=_powershell_dialog_env("フォルダを選択"),
    )


def _select_file_powershell() -> str:
    task_filter = (
        "タスクファイル|*.ziq;*.zit;*.zii;*.zig;*.zia;*.zip|"
        "すべて|*.*"
    )
    env = _powershell_dialog_env("タスクファイルを選択")
    env["TIS_FILE_FILTER"] = task_filter
    return _run_powershell_dialog(_SELECT_FILE_PS, env=env)


# --- Windows Vista+ 共通ダイアログ (IFileOpenDialog / 開発・非配布向け) ---
HRESULT = ctypes.c_long
S_OK = 0
CLSCTX_INPROC_SERVER = 0x1

FOS_PICKFOLDERS = 0x20
FOS_FORCEFILESYSTEM = 0x40
FOS_FILEMUSTEXIST = 0x1000
FOS_PATHMUSTEXIST = 0x800

SIGDN_FILESYSPATH = 0x80058000

CLSID_FileOpenDialog = uuid.UUID("{DC1C5A9C-E88A-4CDE-A481-9E1A61FD0ED4}")
IID_IFileOpenDialog = uuid.UUID("{D57C7288-D4AD-4768-BE02-9D969532D960}")
IID_IShellItem = uuid.UUID("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")

# IFileDialog vtable indices (IUnknown=0..2 の次)
_IFD_SHOW = 3
_IFD_SETFILETYPES = 4
_IFD_SETFILETYPEINDEX = 5
_IFD_SETTITLE = 7
_IFD_SETOPTIONS = 11
_IFD_GETCURRENTSELECTION = 15
# IShellItem::GetDisplayName
_ISI_GETDISPLAYNAME = 5


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class _COMDLG_FILTERSPEC(ctypes.Structure):
    _fields_ = [
        ("pszName", wintypes.LPCWSTR),
        ("pszSpec", wintypes.LPCWSTR),
    ]


def _guid_from_uuid(value: uuid.UUID) -> _GUID:
    g = _GUID()
    g.Data1 = value.time_low
    g.Data2 = value.time_mid
    g.Data3 = value.time_hi_version
    g.Data4 = (wintypes.BYTE * 8)(*value.bytes[8:])
    return g


def _com_release(ptr: ctypes.c_void_p) -> None:
    if not ptr:
        return
    proto = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)
    _com_vtbl_call(ptr, 2, proto)


def _com_vtbl_call(ptr: ctypes.c_void_p, index: int, proto, *args):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[0]
    entry = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index]
    fn = ctypes.cast(entry, proto)
    return fn(ptr, *args)


def _run_sta_dialog(func: Callable[[], str]) -> str:
    """COM ダイアログは STA スレッドで表示する（配布 exe / asyncio スレッド対策）。"""
    result: list[str] = []

    def worker() -> None:
        com_ok = _com_apartment_init()
        try:
            result.append(func())
        finally:
            _com_apartment_uninit(com_ok)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join()
    return result[0] if result else ""


def _create_ifile_open_dialog() -> ctypes.c_void_p | None:
    ole32 = ctypes.windll.ole32
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = HRESULT

    clsid = _guid_from_uuid(CLSID_FileOpenDialog)
    iid = _guid_from_uuid(IID_IFileOpenDialog)
    ptr = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(clsid),
        None,
        CLSCTX_INPROC_SERVER,
        ctypes.byref(iid),
        ctypes.byref(ptr),
    )
    if hr != S_OK:
        return None
    return ptr


def _shell_item_path(item: ctypes.c_void_p) -> str:
    proto = ctypes.WINFUNCTYPE(
        HRESULT,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR),
    )
    psz = wintypes.LPWSTR()
    hr = _com_vtbl_call(item, _ISI_GETDISPLAYNAME, proto, SIGDN_FILESYSPATH, ctypes.byref(psz))
    if hr != S_OK or not psz:
        return ""
    try:
        return psz.value or ""
    finally:
        ctypes.windll.ole32.CoTaskMemFree(psz)


def _ifile_dialog_show(
    *,
    title: str,
    options: int,
    file_types: list[tuple[str, str]] | None = None,
) -> str:
    dialog = _create_ifile_open_dialog()
    if not dialog:
        return ""

    try:
        set_options = ctypes.WINFUNCTYPE(
            HRESULT, ctypes.c_void_p, wintypes.DWORD,
        )
        hr = _com_vtbl_call(dialog, _IFD_SETOPTIONS, set_options, options)
        if hr != S_OK:
            return ""

        set_title = ctypes.WINFUNCTYPE(
            HRESULT, ctypes.c_void_p, wintypes.LPCWSTR,
        )
        hr = _com_vtbl_call(dialog, _IFD_SETTITLE, set_title, title)
        if hr != S_OK:
            return ""

        if file_types:
            specs = [
                _COMDLG_FILTERSPEC(label, pattern)
                for label, pattern in file_types
            ]
            arr = (_COMDLG_FILTERSPEC * len(specs))(*specs)
            set_file_types = ctypes.WINFUNCTYPE(
                HRESULT,
                ctypes.c_void_p,
                wintypes.UINT,
                ctypes.POINTER(_COMDLG_FILTERSPEC),
            )
            hr = _com_vtbl_call(
                dialog, _IFD_SETFILETYPES, set_file_types, len(specs), arr,
            )
            if hr != S_OK:
                return ""
            set_index = ctypes.WINFUNCTYPE(
                HRESULT, ctypes.c_void_p, wintypes.DWORD,
            )
            _com_vtbl_call(dialog, _IFD_SETFILETYPEINDEX, set_index, 1)

        owner = _owner_hwnd()
        if owner:
            ctypes.windll.user32.SetForegroundWindow(owner)

        show = ctypes.WINFUNCTYPE(
            HRESULT, ctypes.c_void_p, wintypes.HWND,
        )
        hr = _com_vtbl_call(dialog, _IFD_SHOW, show, owner or 0)
        if hr != S_OK:
            return ""

        get_selection = ctypes.WINFUNCTYPE(
            HRESULT,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        )
        item = ctypes.c_void_p()
        hr = _com_vtbl_call(
            dialog, _IFD_GETCURRENTSELECTION, get_selection, ctypes.byref(item),
        )
        if hr != S_OK or not item:
            return ""
        try:
            return _shell_item_path(item)
        finally:
            _com_release(item)
    finally:
        _com_release(dialog)


def _select_folder_modern() -> str:
    return _ifile_dialog_show(
        title="フォルダを選択",
        options=FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST,
    )


def _select_file_modern() -> str:
    return _ifile_dialog_show(
        title="タスクファイルを選択",
        options=FOS_FILEMUSTEXIST | FOS_PATHMUSTEXIST | FOS_FORCEFILESYSTEM,
        file_types=TASK_FILE_DIALOG_TYPES,
    )


def _file_filter_string() -> str:
    """GetOpenFileNameW 用のフィルタ文字列（NUL 区切り）。"""
    patterns = []
    for _label, pattern in TASK_FILE_DIALOG_TYPES:
        patterns.append(pattern.replace("*", "").strip())
    ext_glob = ";".join(f"*{p}" for p in patterns if p)
    return f"タスクファイル\0{ext_glob}\0すべて\0*.*\0\0"


def _select_file_win32() -> str:
    """エクスプローラー形式のファイル選択（Vista+ 共通ダイアログ）。"""
    if sys.platform != "win32":
        return ""

    comdlg32 = ctypes.windll.comdlg32
    OFN_EXPLORER = 0x00080000
    OFN_FILEMUSTEXIST = 0x00001000
    OFN_PATHMUSTEXIST = 0x00000800

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", wintypes.LPVOID),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", wintypes.LPVOID),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    buf = ctypes.create_unicode_buffer(32768)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    owner = _owner_hwnd()
    ofn.hwndOwner = owner or None
    ofn.lpstrFilter = _file_filter_string()
    ofn.lpstrFile = buf
    ofn.nMaxFile = len(buf)
    ofn.lpstrTitle = "タスクファイルを選択"
    ofn.Flags = OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST

    if owner:
        ctypes.windll.user32.SetForegroundWindow(owner)

    if comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
        return buf.value
    return ""


def _select_folder_legacy_win32() -> str:
    """IFileOpenDialog 不可時のフォルダ選択フォールバック。"""
    if sys.platform != "win32":
        return ""

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    BIF_RETURNONLYFSDIRS = 0x00000001
    BIF_NEWDIALOGSTYLE = 0x00000040
    MAX_PATH = 32768

    class BROWSEINFOW(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", wintypes.LPVOID),
            ("pszDisplayName", wintypes.LPWSTR),
            ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", wintypes.UINT),
            ("lpfn", wintypes.LPVOID),
            ("lParam", wintypes.LPARAM),
            ("iImage", ctypes.c_int),
        ]

    display_name = ctypes.create_unicode_buffer(MAX_PATH)
    owner = _owner_hwnd()
    bi = BROWSEINFOW()
    bi.hwndOwner = owner or None
    bi.pszDisplayName = display_name
    bi.lpszTitle = "フォルダを選択"
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE

    if owner:
        ctypes.windll.user32.SetForegroundWindow(owner)
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
    if not pidl:
        return ""

    path_buf = ctypes.create_unicode_buffer(MAX_PATH)
    if not shell32.SHGetPathFromIDListW(pidl, path_buf):
        ole32.CoTaskMemFree(pidl)
        return ""
    result = path_buf.value
    ole32.CoTaskMemFree(pidl)
    return result


def _select_folder_pick() -> str:
    path = _select_folder_modern()
    return path or _select_folder_legacy_win32()


def _owner_hwnd() -> int:
    """Win32 共通ダイアログの親ウィンドウ（Flet 本体）を返す。"""
    if sys.platform != "win32":
        return 0

    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
    ]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]

    pid = os.getpid()
    foreground = user32.GetForegroundWindow()
    if foreground:
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(foreground, ctypes.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(foreground):
            return int(foreground)

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM,
    )
    hwnds: list[int] = []

    @WNDENUMPROC
    def cb(hwnd, _):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            hwnds.append(int(hwnd))
        return True

    user32.EnumWindows(cb, 0)
    if hwnds:
        return hwnds[0]

    for title in (
        "タスク画像保存フロー - プレビュー",
        "タスク画像保存フロー",
    ):
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            return int(hwnd)
    return 0


def _com_apartment_init() -> bool:
    """SHBrowseForFolderW 用。自前で初期化した場合のみ uninit する。"""
    if sys.platform != "win32":
        return False
    ole32 = ctypes.windll.ole32
    # S_OK(0) のときだけ CoUninitialize する
    return ole32.CoInitializeEx(None, 0x2) == 0


def _com_apartment_uninit(initialized: bool) -> None:
    if initialized and sys.platform == "win32":
        ctypes.windll.ole32.CoUninitialize()


def select_folder_dialog() -> str:
    """フォルダ選択ダイアログを表示"""
    if _tkinter_available():
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="フォルダを選択")
        root.destroy()
        return folder or ""
    if sys.platform == "win32":
        if _is_packaged_runtime():
            return _select_folder_powershell()
        return _run_sta_dialog(_select_folder_pick)
    return ""


def select_file_dialog() -> str:
    """ファイル選択ダイアログを表示"""
    if _tkinter_available():
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file = filedialog.askopenfilename(
            title="タスクファイルを選択",
            filetypes=TASK_FILE_DIALOG_TYPES,
        )
        root.destroy()
        return file or ""
    if sys.platform == "win32":
        if _is_packaged_runtime():
            return _select_file_powershell()
        return _run_sta_dialog(_select_file_win32)
    return ""
