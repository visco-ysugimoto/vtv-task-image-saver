#!/usr/bin/env python3
"""配布 app フォルダの app.zip / app.zip.hash 整合性を検証する。"""
from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

from sync_python_app_zip import app_zip_hash_path, verify_app_zip_hash


def verify(app_dir: Path) -> int:
    app_zip = app_dir / "data" / "flutter_assets" / "app" / "app.zip"
    hash_path = app_zip_hash_path(app_zip)

    if not app_zip.is_file():
        print(f"FAIL: missing {app_zip}")
        return 1

    digest = hashlib.sha256(app_zip.read_bytes()).hexdigest()
    hash_text = hash_path.read_text(encoding="utf-8").strip() if hash_path.is_file() else ""

    print(f"app.zip     : {app_zip}")
    print(f"sha256      : {digest}")
    print(f"app.zip.hash: {hash_text or '(missing)'}")
    print(f"hash match  : {digest == hash_text}")

    with zipfile.ZipFile(app_zip) as zf:
        ui = zf.read("task_image_saver_ui.py").decode("utf-8")
    markers = {
        "no sidebar drop box": "_build_drop_target" not in ui,
        "full-page dropzone": "wrap_with_task_file_dropzone(" in ui,
        "page.add(root)": "self.page.add(root)" in ui,
    }
    for name, ok in markers.items():
        print(f"ui marker [{name}]: {'OK' if ok else 'FAIL'}")

    ok = verify_app_zip_hash(app_zip) and all(markers.values())
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else base / "dist" / "TaskImageSaver" / "app"
    raise SystemExit(verify(target))
