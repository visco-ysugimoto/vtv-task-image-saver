#!/usr/bin/env python3
"""配布 ZIP の SHA256 サイドカー (.zip.sha256) を生成する。"""
from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from security_limits import write_file_sha256


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: write_release_zip_hash.py <release.zip>")
        return 2

    zip_path = Path(sys.argv[1]).resolve()
    if not zip_path.is_file():
        print(f"ERROR: not found: {zip_path}", file=sys.stderr)
        return 1

    digest = write_file_sha256(zip_path)
    print(f"Wrote {zip_path.name}.sha256")
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
