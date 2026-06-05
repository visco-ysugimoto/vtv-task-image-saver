"""日本語パス対策: app フォルダを ASCII の runtime へ高速同期する。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_VERSION = "1.0.19"
APP_EXE_NAME = "TaskImageSaverApp.exe"
RUNTIME_APP_DIRNAME = "app"
_SYNC_IGNORE_NAMES = frozenset({".app_version", "startup.log"})


def runtime_deploy_dir() -> Path:
    return (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "VISCO"
        / "TaskImageSaver"
        / "runtime"
    )


def resolve_source_app_dir(install_or_app: Path) -> Path:
    """配布ルートまたは app フォルダから同期元 app ディレクトリを決める。"""
    app_subdir = install_or_app / RUNTIME_APP_DIRNAME
    if (app_subdir / APP_EXE_NAME).is_file():
        return app_subdir
    if (app_subdir / "flutter_windows.dll").is_file():
        return app_subdir
    return install_or_app


def resolve_install_root(app_dir: Path) -> Path:
    """app フォルダから配布ルート（設定ファイルの基準）を推定する。"""
    parent = app_dir.parent
    if (parent / "TaskImageSaver.exe").is_file():
        return parent
    return app_dir


def runtime_app_dir(runtime_root: Path | None = None) -> Path:
    root = runtime_root if runtime_root is not None else runtime_deploy_dir()
    return root / RUNTIME_APP_DIRNAME


def path_has_non_ascii(path: Path | str) -> bool:
    try:
        str(path).encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def _same_drive(left: Path, right: Path) -> bool:
    return (
        os.path.splitdrive(str(left.resolve()))[0].lower()
        == os.path.splitdrive(str(right.resolve()))[0].lower()
    )


def _resolve_app_exe(app_dir: Path) -> Path | None:
    for name in (APP_EXE_NAME, "TaskImageSaver.exe"):
        candidate = app_dir / name
        if candidate.is_file():
            return candidate
    return None


def _ignore_sync(_directory: str, names: list[str]) -> list[str]:
    return [name for name in names if name in _SYNC_IGNORE_NAMES]


def _has_legacy_flat_runtime(runtime_root: Path) -> bool:
    if (runtime_root / "flutter_windows.dll").is_file():
        return True
    for name in (APP_EXE_NAME, "TaskImageSaver.exe"):
        if (runtime_root / name).is_file():
            return True
    return False


def needs_app_resync(source_app: Path, dest_app: Path) -> bool:
    if not dest_app.is_dir():
        return True
    dest_exe = _resolve_app_exe(dest_app)
    if dest_exe is None:
        return True
    version_file = dest_app / ".app_version"
    if not version_file.is_file():
        return True
    if version_file.read_text(encoding="utf-8").strip() != APP_VERSION:
        return True
    src_exe = _resolve_app_exe(source_app)
    if src_exe is None:
        return True
    if src_exe.stat().st_mtime > dest_exe.stat().st_mtime:
        return True
    return False


def _cleanup_runtime_root(runtime_root: Path) -> None:
    dest_app = runtime_app_dir(runtime_root)
    if dest_app.exists():
        shutil.rmtree(dest_app)
    if _has_legacy_flat_runtime(runtime_root):
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)


def _hardlink_tree(source: Path, dest: Path) -> bool:
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for root, _dirs, files in os.walk(source):
            rel = Path(root).relative_to(source)
            target_dir = dest / rel
            target_dir.mkdir(parents=True, exist_ok=True)
            for filename in files:
                if filename in _SYNC_IGNORE_NAMES:
                    continue
                src_file = Path(root) / filename
                dst_file = target_dir / filename
                if dst_file.exists() or dst_file.is_symlink():
                    dst_file.unlink()
                os.link(src_file, dst_file)
        return True
    except OSError:
        if dest.exists():
            shutil.rmtree(dest)
        return False


def _robocopy_mirror(source: Path, dest: Path) -> bool:
    if sys.platform != "win32":
        return False
    dest.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "robocopy",
            str(source),
            str(dest),
            "/MIR",
            "/MT:8",
            "/R:1",
            "/W:1",
            "/NFL",
            "/NDL",
            "/NJH",
            "/NJS",
            "/nc",
            "/ns",
            "/np",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode < 8


def _copytree_mirror(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        dest,
        ignore=_ignore_sync,
        dirs_exist_ok=True,
    )


def _materialize_app_tree(source_app: Path, dest_app: Path) -> str:
    if _same_drive(source_app, dest_app) and _hardlink_tree(source_app, dest_app):
        return "hardlink"
    if dest_app.exists():
        shutil.rmtree(dest_app)
    if _robocopy_mirror(source_app, dest_app):
        return "robocopy"
    _copytree_mirror(source_app, dest_app)
    return "copytree"


def sync_app_to_runtime(source_app: Path, runtime_root: Path | None = None) -> Path:
    """
    source_app を runtime/<app>/ へ同期する。

    同一ドライブではハードリンク、失敗時は robocopy、最後は copytree。
    戻り値は同期先 app ディレクトリ。
    """
    source_app = source_app.resolve()
    root = (runtime_root if runtime_root is not None else runtime_deploy_dir()).resolve()
    dest_app = runtime_app_dir(root)

    root.mkdir(parents=True, exist_ok=True)
    if needs_app_resync(source_app, dest_app) or _has_legacy_flat_runtime(root):
        _cleanup_runtime_root(root)

    if not dest_app.is_dir():
        mode = _materialize_app_tree(source_app, dest_app)
        (dest_app / ".app_version").write_text(APP_VERSION, encoding="utf-8")
        (dest_app / ".sync_mode").write_text(mode, encoding="utf-8")

    return dest_app
