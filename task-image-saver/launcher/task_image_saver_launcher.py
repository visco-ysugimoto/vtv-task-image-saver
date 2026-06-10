"""
配布用ランチャー（Flutter 非同梱）。

TaskImageSaver.exe から起動し、パスに非 ASCII がある場合は
%LOCALAPPDATA% へ app フォルダのみ同期して TaskImageSaverApp.exe を起動する。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from launch_handoff import write_pending_launch
from runtime_sync import (
    APP_EXE_NAME,
    path_has_non_ascii,
    resolve_source_app_dir,
    runtime_deploy_dir,
    sync_app_to_runtime,
)
RUNTIME_ENV = "TASK_IMAGE_SAVER_RUNTIME"
INSTALL_ENV = "TASK_IMAGE_SAVER_INSTALL_DIR"
LAUNCH_FILE_ENV = "TASK_IMAGE_SAVER_LAUNCH_FILE"


def _install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resolve_app_exe(install: Path) -> Path | None:
    app_subdir = install / "app"
    app = app_subdir / APP_EXE_NAME
    if app.is_file():
        return app
    legacy_subdir = app_subdir / "TaskImageSaver.exe"
    if legacy_subdir.is_file() and (app_subdir / "flutter_windows.dll").is_file():
        return legacy_subdir

    app = install / APP_EXE_NAME
    if app.is_file():
        return app
    legacy = install / "TaskImageSaver.exe"
    if legacy.is_file() and (install / "flutter_windows.dll").is_file():
        return legacy
    return None


def _show_error(message: str) -> None:
    if sys.platform != "win32":
        print(message, file=sys.stderr)
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            None, message, "TaskImageSaver", 0x10,
        )
    except Exception:
        print(message, file=sys.stderr)


def _list_subst_targets() -> dict[str, str]:
    result = subprocess.run(
        ["subst"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    mapping: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=>" not in line:
            continue
        left, right = line.split("=>", 1)
        drive = left.strip().rstrip(":").upper()
        if len(drive) == 1:
            mapping[drive] = right.strip()
    return mapping


def _find_or_create_subst_drive(install: Path) -> str | None:
    install_norm = str(install.resolve()).rstrip("\\").lower()
    for drive, target in _list_subst_targets().items():
        if target.rstrip("\\").lower() == install_norm:
            return drive
    for letter in "TUVWXYZ":
        drive = f"{letter}:"
        proc = subprocess.run(
            ["subst", drive, str(install)],
            capture_output=True,
        )
        if proc.returncode == 0:
            return letter
    return None


def _refresh_flet_cache_if_needed(install: Path) -> None:
    """app.zip 更新時に Roaming の Flet 増分キャッシュ不整合を防ぐ。"""
    if sys.platform != "win32":
        return
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return
    hash_path = (
        install / "app" / "data" / "flutter_assets" / "app" / "app.zip.hash"
    )
    if not hash_path.is_file():
        return
    expected = hash_path.read_text(encoding="utf-8").strip()
    if not expected:
        return
    state_dir = Path(appdata) / "VISCO" / "TaskImageSaver"
    marker = state_dir / "flet_app_zip.hash"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == expected:
        return
    cache = state_dir / "flet"
    if cache.exists():
        shutil.rmtree(cache)
    state_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text(expected, encoding="utf-8")


def _apply_launch_args_to_env(env: dict[str, str], args: list[str]) -> None:
    """右クリック等の引数を環境変数へ渡す（Flet 同梱 exe は sys.argv を受け取れない場合がある）。"""
    for raw in args:
        candidate = raw.strip().strip('"')
        if not candidate or candidate.startswith("-"):
            continue
        path = Path(candidate)
        if not path.is_absolute():
            path = Path.cwd() / path
        resolved = str(path.resolve())
        env[LAUNCH_FILE_ENV] = resolved
        write_pending_launch(resolved)
        return


def _replace_with_app(exe: Path, cwd: Path, install_dir: Path, args: list[str]) -> None:
    """
    ランチャー・プロセスを Flet 本体に置き換える。

    subprocess で二重起動すると体感が遅くなるため、環境変数を整えて exec する。
    ファイルパスは argv では渡さない（Dropzone 競合回避）。
    """
    env = os.environ.copy()
    env[RUNTIME_ENV] = "1"
    env[INSTALL_ENV] = str(install_dir)
    _apply_launch_args_to_env(env, args)
    os.chdir(cwd)
    os.execve(str(exe), [exe.name], env)


def main() -> int:
    install = _install_root()
    _refresh_flet_cache_if_needed(install)
    app_exe = _resolve_app_exe(install)
    if app_exe is None:
        _show_error(
            f"{APP_EXE_NAME} が見つかりません。\n"
            f"フォルダごと展開されているか確認してください。\n{install}"
        )
        return 1

    args = sys.argv[1:]
    if not path_has_non_ascii(install):
        _replace_with_app(app_exe, install, install, args)

    if os.environ.get(RUNTIME_ENV) == "1":
        install_dir = Path(os.environ.get(INSTALL_ENV, str(install)))
        _replace_with_app(app_exe, install, install_dir, args)

    runtime_root = runtime_deploy_dir()
    source_app = resolve_source_app_dir(install)
    dest_app = sync_app_to_runtime(source_app, runtime_root)
    runtime_exe = _resolve_app_exe(dest_app)
    if runtime_exe is not None:
        _replace_with_app(runtime_exe, runtime_root, install, args)

    letter = _find_or_create_subst_drive(install)
    if letter:
        subst_root = Path(f"{letter}:/")
        subst_exe = subst_root / app_exe.name
        if subst_exe.is_file():
            _replace_with_app(subst_exe, subst_root, install, args)

    _show_error(
        "日本語を含むフォルダからの起動に失敗しました。\n"
        "コピー先へ書き込めないか、必要なファイルが不足しています。\n"
        f"インストール先: {install}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
