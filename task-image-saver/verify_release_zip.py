#!/usr/bin/env python3
"""配布 ZIP と同梱の .sha256 の整合性を検証する。"""
from __future__ import annotations

import sys
from pathlib import Path

from security_limits import verify_file_sha256


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: verify_release_zip.py <path/to/TaskImageSaver_vX_win64.zip>")
        return 2

    zip_path = Path(sys.argv[1]).resolve()
    hash_path = zip_path.with_suffix(zip_path.suffix + ".sha256")

    if not zip_path.is_file():
        print(f"FAIL: ZIP not found: {zip_path}")
        return 1
    if not hash_path.is_file():
        print(f"FAIL: hash file not found: {hash_path}")
        return 1

    ok = verify_file_sha256(zip_path, hash_path)
    print(f"zip       : {zip_path}")
    print(f"hash file : {hash_path}")
    print(f"expected  : {hash_path.read_text(encoding='utf-8').strip()}")
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
