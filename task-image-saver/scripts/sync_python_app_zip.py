#!/usr/bin/env python3
"""Flet app.zip 内の Python ソースを更新し app.zip.hash を同期する。"""
from __future__ import annotations

import hashlib
import py_compile
import sys
import zipfile
from pathlib import Path

APP_PY_FILES = [
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
]


def app_zip_hash_path(app_zip: Path) -> Path:
    return app_zip.parent / f"{app_zip.name}.hash"


def write_app_zip_hash(app_zip: Path) -> str:
    digest = hashlib.sha256(app_zip.read_bytes()).hexdigest()
    hash_path = app_zip_hash_path(app_zip)
    hash_path.write_text(digest, encoding="utf-8")
    return digest


def verify_app_zip_hash(app_zip: Path) -> bool:
    hash_path = app_zip_hash_path(app_zip)
    if not app_zip.is_file() or not hash_path.is_file():
        return False
    digest = hashlib.sha256(app_zip.read_bytes()).hexdigest()
    return hash_path.read_text(encoding="utf-8").strip() == digest


def _verify_python_syntax(src_dir: Path) -> int:
    errors = 0
    for name in APP_PY_FILES:
        path = src_dir / name
        if not path.is_file():
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            print(f"Syntax error in {name}: {exc}", file=sys.stderr)
            errors += 1
    return errors


def sync_app_zip(app_zip: Path, src_dir: Path) -> int:
    if not app_zip.is_file():
        print(f"app.zip not found: {app_zip}", file=sys.stderr)
        return 1

    syntax_errors = _verify_python_syntax(src_dir)
    if syntax_errors:
        print(f"Aborting sync: {syntax_errors} Python file(s) have syntax errors.", file=sys.stderr)
        return 1

    replace = {
        name: (src_dir / name).read_bytes()
        for name in APP_PY_FILES
        if (src_dir / name).is_file()
    }

    with zipfile.ZipFile(app_zip, "r") as zf:
        kept: list[tuple[str, bytes, int]] = []
        for info in zf.infolist():
            if info.filename in replace:
                continue
            kept.append((info.filename, zf.read(info.filename), info.external_attr))

    tmp = app_zip.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name, data, ext_attr in kept:
            zi = zipfile.ZipInfo(name)
            zi.external_attr = ext_attr
            out.writestr(zi, data)
        for name, data in replace.items():
            out.writestr(name, data)
            print(f"  updated: {name}")

    tmp.replace(app_zip)
    digest = write_app_zip_hash(app_zip)
    print(f"Synced {len(replace)} file(s) -> {app_zip}")
    print(f"Updated app.zip.hash -> {digest[:16]}...")
    if not verify_app_zip_hash(app_zip):
        print("ERROR: app.zip.hash verification failed", file=sys.stderr)
        return 1
    return 0


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def app_source_dir() -> Path:
    return project_root() / "app"


if __name__ == "__main__":
    root = project_root()
    default_zip = (
        root / "build" / "windows" / "data" / "flutter_assets" / "app" / "app.zip"
    )
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default_zip
    raise SystemExit(sync_app_zip(target, app_source_dir()))
