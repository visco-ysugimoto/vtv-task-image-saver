"""ランチャーから Flet 本体へタスクファイルパスを渡す（環境変数の補助）。"""
from __future__ import annotations

import json
import os
import sys
import time
import zipfile
from pathlib import Path

_PENDING_MAX_AGE_SEC = 120.0

# sync_python_app_zip.APP_PY_FILES と揃える（Flet 増分キャッシュ検証用）
_REQUIRED_APP_PY_FILES = (
    "app_runtime.py",
    "runtime_sync.py",
    "config.py",
    "flet_dropzone_support.py",
    "flet_resources.py",
    "flet_ui_constants.py",
    "launch_handoff.py",
    "main_save_task_images_flet.py",
    "save_task_images_CamNum_selection.py",
    "security_limits.py",
    "task_image_saver_logic.py",
    "task_image_saver_ui.py",
    "utils.py",
)


def _flet_app_cache_dir() -> Path | None:
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return None
    return Path(appdata) / "VISCO" / "TaskImageSaver" / "flet" / "app"


def _app_zip_in_app_dir(app_dir: Path) -> Path | None:
    app_zip = app_dir / "data" / "flutter_assets" / "app" / "app.zip"
    return app_zip if app_zip.is_file() else None


def _packaged_app_zip() -> Path | None:
    if sys.platform != "win32":
        return None

    install = os.environ.get("TASK_IMAGE_SAVER_INSTALL_DIR", "").strip()
    if install:
        install_path = Path(install)
        for candidate in (install_path / "app", install_path):
            app_zip = _app_zip_in_app_dir(candidate)
            if app_zip is not None:
                return app_zip

    exe = Path(sys.executable).resolve()
    if exe.suffix.lower() != ".exe":
        return None
    if not (exe.parent / "flutter_windows.dll").is_file():
        return None
    return _app_zip_in_app_dir(exe.parent)


def ensure_flet_app_cache_complete() -> None:
    """
    Flet の Roaming キャッシュが app.zip と不整合なとき全展開し直す。

    app.zip.hash 更新後も増分展開だけが走り、新規モジュールが欠落することがある。
    """
    app_zip = _packaged_app_zip()
    cache_dir = _flet_app_cache_dir()
    if app_zip is None or cache_dir is None:
        return

    hash_path = app_zip.parent / "app.zip.hash"
    expected_hash = (
        hash_path.read_text(encoding="utf-8").strip()
        if hash_path.is_file()
        else ""
    )
    cache_hash_path = cache_dir / ".hash"
    cache_hash = (
        cache_hash_path.read_text(encoding="utf-8").strip()
        if cache_hash_path.is_file()
        else ""
    )

    missing_py = [
        name for name in _REQUIRED_APP_PY_FILES
        if not (cache_dir / name).is_file()
    ]
    needs_refresh = bool(missing_py)
    if expected_hash and cache_hash != expected_hash:
        needs_refresh = True

    if not needs_refresh:
        return

    cache_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(app_zip) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = cache_dir / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info.filename))

    if expected_hash:
        cache_hash_path.write_text(expected_hash, encoding="utf-8")


def pending_launch_path() -> Path:
    return (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "VISCO"
        / "TaskImageSaver"
        / "pending_launch.json"
    )


def write_pending_launch(task_file: str) -> None:
    path = pending_launch_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"file": os.path.abspath(task_file)}, ensure_ascii=False),
        encoding="utf-8",
    )


def read_and_clear_pending_launch() -> str | None:
    path = pending_launch_path()
    if not path.is_file():
        return None
    try:
        if time.time() - path.stat().st_mtime > _PENDING_MAX_AGE_SEC:
            path.unlink(missing_ok=True)
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        file_path = data.get("file", "")
        return os.path.abspath(file_path) if file_path else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
