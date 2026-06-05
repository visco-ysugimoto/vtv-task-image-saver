"""配布版 Flet アプリ向けのパス解決・起動ログ・日本語パス対策。"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from launch_handoff import write_pending_launch
from runtime_sync import (
    APP_EXE_NAME,
    path_has_non_ascii,
    resolve_install_root,
    runtime_deploy_dir,
    sync_app_to_runtime,
)

_RUNTIME_ENV = "TASK_IMAGE_SAVER_RUNTIME"
_INSTALL_DIR_ENV = "TASK_IMAGE_SAVER_INSTALL_DIR"
_LAUNCH_FILE_ENV = "TASK_IMAGE_SAVER_LAUNCH_FILE"


def is_packaged_app() -> bool:
    """flet build 済みの TaskImageSaverApp.exe から起動しているか。"""
    if sys.platform != "win32":
        return False
    exe = Path(sys.executable).resolve()
    if exe.suffix.lower() != ".exe":
        return False
    if exe.name.lower() in ("python.exe", "pythonw.exe", "flet.exe"):
        return False
    if exe.name.lower() == APP_EXE_NAME.lower():
        return (exe.parent / "flutter_windows.dll").is_file()
    return (exe.parent / "flutter_windows.dll").is_file()


def install_dir() -> Path | None:
    """日本語パスからリダイレクト起動した場合の元インストール先。"""
    raw = os.environ.get(_INSTALL_DIR_ENV, "").strip()
    if not raw:
        return None
    return Path(raw)


def app_root() -> Path:
    if is_packaged_app():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def ensure_ascii_runtime_exit() -> None:
    """
    インストールパスに非 ASCII 文字がある場合、ASCII の runtime へ同期して再起動する。

    Flutter/Flet の Windows 版は日本語等を含む exe パスでネイティブクラッシュするため。
    """
    if sys.platform != "win32" or not is_packaged_app():
        return
    if os.environ.get(_RUNTIME_ENV) == "1":
        return

    source_app = app_root()
    if not path_has_non_ascii(source_app):
        return

    runtime_root = runtime_deploy_dir()
    dest_app = sync_app_to_runtime(source_app, runtime_root)
    runtime_exe = dest_app / APP_EXE_NAME
    if not runtime_exe.is_file():
        runtime_exe = dest_app / "TaskImageSaver.exe"
    if not runtime_exe.is_file():
        return

    install_root = resolve_install_root(source_app)
    env = os.environ.copy()
    env[_RUNTIME_ENV] = "1"
    env[_INSTALL_DIR_ENV] = str(install_root)
    for raw in sys.argv[1:]:
        candidate = raw.strip().strip('"')
        if candidate and not candidate.startswith("-"):
            abs_path = os.path.abspath(candidate)
            env[_LAUNCH_FILE_ENV] = abs_path
            write_pending_launch(abs_path)
            break
    os.chdir(runtime_root)
    os.execve(str(runtime_exe), [runtime_exe.name], env)


def _debug_logging_enabled() -> bool:
    return os.environ.get("TASK_IMAGE_SAVER_DEBUG", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def log_launch_resolution(path: str | None, source: str) -> None:
    """右クリック起動のパス解決結果を記録する（トラブルシュート用）。"""
    if not _debug_logging_enabled():
        return
    log_path = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "VISCO"
        / "TaskImageSaver"
        / "launch_debug.log"
    )
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime

        line = (
            f"{datetime.now().isoformat(timespec='seconds')} "
            f"source={source} path={path!r} argv={sys.argv!r}\n"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def setup_runtime() -> None:
    """作業ディレクトリを exe 横にし、未処理例外をログへ書く。"""
    from security_limits import configure_pillow_limits

    configure_pillow_limits()
    root = app_root()
    os.chdir(root)
    _install_exception_logging(root)


def _install_exception_logging(root: Path) -> None:
    log_paths = [
        root / "startup.log",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "VISCO"
        / "TaskImageSaver"
        / "startup.log",
    ]
    install = install_dir()
    if install:
        log_paths.append(install / "startup.log")

    def _hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        for path in log_paths:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(text)
                    f.write("\n")
            except OSError:
                pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
