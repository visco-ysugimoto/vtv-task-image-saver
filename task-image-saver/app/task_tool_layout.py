"""
タスクのツール構成。

cammaster_seq.log の有効ツールと、同じフォルダの t{task}_{cam}_{row}.tsk
（カメラ・行は 0 始まり）のうちログに無い無効ツールをまとめる。
列見出しの名称は title に後から入れられる。空なら番号だけ表示する。
"""
from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass, field

from security_limits import read_zip_member_prefix

_HEAD_RE = re.compile(
    r"^\((\d+)\s*,\s*(\d+)\s*:\s*(\d+)\)\s*:\s*(.+?)\s*,\s*name\s*=\s*(.*)$"
)
_LINK_RE = re.compile(
    r",\s*(ref|coor)\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*:\s*name\s*=\s*([^,]*)"
)
_TSK_RE = re.compile(r"^t(\d+)_(\d{2})_(\d{2})\.tsk$", re.IGNORECASE)

_TSK_HEADER_BYTES = 4096
_LOG_PREFIX_BYTES = 1_000_000
_LABEL_MAX_CHARS = 80


@dataclass
class ToolLink:
    """ref / coor が指すツール。カメラと行は 1 始まり。"""

    camera: int
    row: int
    name: str


@dataclass
class ToolCell:
    """グリッド上の 1 ツール。"""

    camera: int
    row: int
    tool_id: int | None
    tool_name: str
    comment: str
    enabled: bool
    ref: ToolLink | None = None
    coor: ToolLink | None = None


@dataclass
class CameraColumn:
    """カメラ列。title が空のときは [番号] だけ出す。"""

    number: int
    title: str = ""


@dataclass
class ToolLayout:
    cameras: list[CameraColumn] = field(default_factory=list)
    tools: list[ToolCell] = field(default_factory=list)
    max_row: int = 0

    def tool_at(self, camera: int, row: int) -> ToolCell | None:
        for tool in self.tools:
            if tool.camera == camera and tool.row == row:
                return tool
        return None


def parse_cammaster_seq_text(text: str) -> list[ToolCell]:
    """cammaster_seq.log 本文から有効ツールを出現順に返す。"""
    tools: list[ToolCell] = []
    seen: set[tuple[int, int]] = set()
    if not text:
        return tools
    for line in text.splitlines():
        tool = _parse_cammaster_line(line.strip())
        if tool is None:
            continue
        key = (tool.camera, tool.row)
        if key in seen:
            continue
        seen.add(key)
        tools.append(tool)
    return tools


def load_tool_layout_from_folder(task_dir: str) -> ToolLayout:
    """タスクフォルダ（img の親）からツール構成を読む。"""
    if not task_dir or not os.path.isdir(task_dir):
        return ToolLayout()
    log_path = os.path.join(task_dir, "cammaster_seq.log")
    text = _read_text_file(log_path) if os.path.isfile(log_path) else ""
    tools = parse_cammaster_seq_text(text)
    occupied = {(tool.camera, tool.row) for tool in tools}
    for name in sorted(os.listdir(task_dir)):
        placed = _tsk_position(name)
        if placed is None or placed in occupied:
            continue
        camera, row = placed
        header = _read_file_prefix(os.path.join(task_dir, name), _TSK_HEADER_BYTES)
        tool_name, comment = extract_tsk_labels(header)
        tools.append(_disabled_tool(camera, row, tool_name, comment))
        occupied.add(placed)
    return _build_layout(tools)


def load_tool_layout_from_zip(zip_path: str, task_prefix: str) -> ToolLayout:
    """タスクファイル内の 1 タスクからツール構成を読む。"""
    if not zip_path or not os.path.isfile(zip_path) or not task_prefix:
        return ToolLayout()
    prefix = task_prefix.replace("\\", "/").strip("/")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        raw_names = zip_ref.namelist()
        normalized = [name.replace("\\", "/") for name in raw_names]
        log_raw = _find_member(
            normalized,
            raw_names,
            prefix,
            "cammaster_seq.log",
        )
        text = ""
        if log_raw:
            text = _decode_bytes(
                read_zip_member_prefix(zip_ref, log_raw, _LOG_PREFIX_BYTES)
            )
        tools = parse_cammaster_seq_text(text)
        occupied = {(tool.camera, tool.row) for tool in tools}
        tsk_members: list[tuple[str, int, int]] = []
        for norm_name, raw_name in zip(normalized, raw_names):
            if not _is_under_prefix(norm_name, prefix):
                continue
            placed = _tsk_position(os.path.basename(norm_name))
            if placed is None or placed in occupied:
                continue
            tsk_members.append((raw_name, placed[0], placed[1]))
        for raw_name, camera, row in sorted(tsk_members, key=lambda item: (item[1], item[2])):
            key = (camera, row)
            if key in occupied:
                continue
            header = read_zip_member_prefix(zip_ref, raw_name, _TSK_HEADER_BYTES)
            tool_name, comment = extract_tsk_labels(header)
            tools.append(_disabled_tool(camera, row, tool_name, comment))
            occupied.add(key)
    return _build_layout(tools)


def extract_tsk_labels(data: bytes) -> tuple[str, str]:
    """tsk 先頭の長さ付き UTF-16 文字列からツール名とコメントを取る。"""
    found: list[str] = []
    size = len(data)
    index = 0
    while index + 6 <= size and len(found) < 2:
        length = int.from_bytes(data[index:index + 4], "little")
        byte_len = length * 2
        end = index + 4 + byte_len
        if 1 <= length <= _LABEL_MAX_CHARS and end <= size:
            text = data[index + 4:end].decode("utf-16-le", errors="ignore")
            if _is_tool_label(text) and len(text) == length:
                found.append(text)
                index = end
                continue
        index += 1
    tool_name = found[0] if found else ""
    comment = found[1] if len(found) > 1 else ""
    return tool_name, comment


def _parse_cammaster_line(line: str) -> ToolCell | None:
    match = _HEAD_RE.match(line)
    if not match:
        return None
    camera = int(match.group(1))
    row = int(match.group(2))
    tool_id = int(match.group(3))
    tool_name = match.group(4).strip()
    rest = match.group(5)
    links = list(_LINK_RE.finditer(rest))
    if links:
        comment = rest[:links[0].start()].strip()
    else:
        comment = rest.strip()
    ref = None
    coor = None
    for link in links:
        parsed = _parse_link(
            link.group(1),
            int(link.group(2)),
            int(link.group(3)),
            link.group(4),
            camera,
            row,
        )
        if parsed is None:
            continue
        kind, tool_link = parsed
        if kind == "ref":
            ref = tool_link
        else:
            coor = tool_link
    if camera <= 0 or row <= 0 or not tool_name:
        return None
    return ToolCell(
        camera=camera,
        row=row,
        tool_id=tool_id,
        tool_name=tool_name,
        comment=comment,
        enabled=True,
        ref=ref,
        coor=coor,
    )


def _parse_link(
    kind: str,
    camera: int,
    row: int,
    name: str,
    self_camera: int,
    self_row: int,
) -> tuple[str, ToolLink] | None:
    label = name.strip()
    if camera == 0 and row == 0:
        return None
    if not label or label.lower() == "none":
        return None
    if camera == self_camera and row == self_row:
        return None
    if camera <= 0 or row <= 0:
        return None
    return kind, ToolLink(camera=camera, row=row, name=label)


def _tsk_position(filename: str) -> tuple[int, int] | None:
    match = _TSK_RE.match(filename)
    if not match:
        return None
    camera0 = int(match.group(2))
    row0 = int(match.group(3))
    if camera0 == 99:
        return None
    return camera0 + 1, row0 + 1


def _disabled_tool(camera: int, row: int, tool_name: str, comment: str) -> ToolCell:
    return ToolCell(
        camera=camera,
        row=row,
        tool_id=None,
        tool_name=tool_name or "（名称不明）",
        comment=comment,
        enabled=False,
    )


def _build_layout(tools: list[ToolCell]) -> ToolLayout:
    cameras = [
        CameraColumn(number=number)
        for number in sorted({tool.camera for tool in tools})
    ]
    max_row = max((tool.row for tool in tools), default=0)
    ordered = sorted(tools, key=lambda tool: (tool.camera, tool.row))
    return ToolLayout(cameras=cameras, tools=ordered, max_row=max_row)


def _is_tool_label(text: str) -> bool:
    if not text or any(ch in text for ch in "\\/."):
        return False
    has_letter = False
    for ch in text:
        if ch in " +-_":
            continue
        if ch.isdigit():
            continue
        code = ord(ch)
        is_ascii = ("A" <= ch <= "Z") or ("a" <= ch <= "z")
        is_jp = (
            0x3040 <= code <= 0x30FF
            or 0x4E00 <= code <= 0x9FFF
            or 0xFF00 <= code <= 0xFFEF
        )
        if not is_ascii and not is_jp:
            return False
        has_letter = True
    return has_letter


def _is_under_prefix(norm_name: str, prefix: str) -> bool:
    if not prefix:
        return False
    return norm_name == prefix or norm_name.startswith(prefix + "/")


def _find_member(
    normalized: list[str],
    raw_names: list[str],
    prefix: str,
    basename: str,
) -> str | None:
    wanted = basename.casefold()
    exact = f"{prefix}/{basename}" if prefix else basename
    fallback = None
    for norm_name, raw_name in zip(normalized, raw_names):
        if not _is_under_prefix(norm_name, prefix):
            continue
        if os.path.basename(norm_name).casefold() != wanted:
            continue
        if norm_name.casefold() == exact.casefold():
            return raw_name
        if fallback is None:
            fallback = raw_name
    return fallback


def _read_text_file(path: str) -> str:
    with open(path, "rb") as file:
        return _decode_bytes(file.read())


def _read_file_prefix(path: str, max_bytes: int) -> bytes:
    with open(path, "rb") as file:
        return file.read(max_bytes)


def _decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
