"""ランチャーから Flet 本体へタスクファイルパスを渡す（環境変数の補助）。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

_PENDING_MAX_AGE_SEC = 120.0


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
