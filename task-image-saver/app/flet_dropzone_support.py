"""
デスクトップ向け OS ファイルドロップ。

``flet-dropzone``（Flutter ``desktop_drop``）は ``flet build windows`` 済み
クライアントでのみ使用する。パッケージだけ入っていても標準 flet.exe では
「Unknown control」になる。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Awaitable, Callable, Optional

import flet as ft

_SCRIPT_DIR = Path(__file__).resolve().parent
_DROP_HOOK_ERROR: Optional[str] = None


def _dropzone_module():
    try:
        import flet_dropzone as ftd  # noqa: F401
        return ftd
    except ImportError:
        return None


def is_file_dropzone_available() -> bool:
    """``flet-dropzone`` パッケージがインストールされているか。"""
    return _dropzone_module() is not None


def is_packaged_flet_executable() -> bool:
    """配布フォルダ内の Flet 本体 exe（flutter_windows.dll 同梱）か。"""
    if sys.platform != "win32":
        return False
    exe = Path(sys.executable).resolve()
    if exe.suffix.lower() != ".exe":
        return False
    if exe.name.lower() in ("python.exe", "pythonw.exe", "flet.exe"):
        return False
    if exe.name.lower() in ("taskimagesaver.exe", "taskimagesaverapp.exe"):
        return (exe.parent / "flutter_windows.dll").is_file()
    return False


def is_dropzone_client_built() -> bool:
    """
    Dropzone 対応の Flet クライアントで動作しているか。

    開発時は ``build\\windows\\*.exe``、配布時は exe 同梱の Flutter ランタイムで判定。
    """
    if is_packaged_flet_executable():
        return True
    if sys.platform != "win32":
        return False
    build_dir = _SCRIPT_DIR / "build" / "windows"
    if not build_dir.is_dir():
        return False
    return any(build_dir.glob("*.exe"))


def should_use_file_dropzone() -> bool:
    if os.environ.get("TASK_IMAGE_SAVER_NO_DROPZONE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return False
    return is_file_dropzone_available() and is_dropzone_client_built()


def dropzone_import_error() -> Optional[str]:
    return _DROP_HOOK_ERROR


def dropzone_setup_hint() -> str:
    if not is_file_dropzone_available():
        return "pip install flet-dropzone"
    if not is_dropzone_client_built():
        return (
            "task-image-saver フォルダで "
            "「flet build windows -v」を一度実行してください"
        )
    return ""


def wrap_with_task_file_dropzone(
    content: ft.Control,
    on_task_file: Callable[[str], Awaitable[None]],
    page: ft.Page,
    *,
    allowed_extensions: Optional[list[str]] = None,
) -> ft.Control:
    """
    画面全体を Dropzone で包む。ドロップ時に ``on_task_file(path)`` を呼ぶ。
    未対応クライアントでは ``content`` をそのまま返す。
    """
    global _DROP_HOOK_ERROR
    if not should_use_file_dropzone():
        if is_file_dropzone_available() and not is_dropzone_client_built():
            _DROP_HOOK_ERROR = dropzone_setup_hint()
        return content

    ftd = _dropzone_module()
    if ftd is None:
        _DROP_HOOK_ERROR = "flet-dropzone が未インストールです (pip install flet-dropzone)"
        return content

    exts = allowed_extensions or ["ziq", "zit", "zii", "zig", "zia", "zip"]

    def on_dropped(e):
        files = getattr(e, "files", None) or []
        if not files:
            return
        path = os.path.abspath(str(files[0]).strip().strip('"'))
        if not path:
            return
        page.run_task(on_task_file, path)

    return ftd.Dropzone(
        content=content,
        expand=True,
        allowed_file_types=exts,
        on_dropped=on_dropped,
    )


def install_windows_file_drop(*_args, **_kwargs) -> bool:
    """後方互換。Win32 フックは使用しない。"""
    return should_use_file_dropzone()


def refresh_windows_file_drop(*_args, **_kwargs) -> int:
    return 0
