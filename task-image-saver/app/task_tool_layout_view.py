"""ツール構成をカメラ列×行のグリッドとして描く。"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import flet as ft
import flet.canvas as cv
from PIL import Image, ImageDraw, ImageFont

from task_tool_layout import CameraColumn, ToolCell, ToolLayout

_PAD = 8
_ROW_HEADER_W = 44
_COL_HEADER_H = 34
_CELL_W = 188
_CELL_H = 46
_GUTTER = 36
_V_GAP = 8
_SLOT_W = _CELL_W + _GUTTER
_SLOT_H = _CELL_H + _V_GAP
_REF_RAIL = 8
_COOR_RAIL = 20
_LANE_PITCH = 8
_ARROW_LEN = 8
_ARROW_HALF = 3.5
# 同じセルに付く ref と coor が重ならないよう、赤は上、青は下にずらす。
_LANE_OFFSET = 11


@dataclass(frozen=True)
class _Metrics:
    """画面と PNG 書き出しで共有するグリッド寸法。"""

    cell_h: float
    v_gap: float
    col_header_h: float
    name_size: int
    comment_size: int
    header_size: int
    lane_offset: float
    mark_size: int
    pad_y: float


_NORMAL = _Metrics(46, 8, 34, 11, 11, 12, 11, 16, 2)
_COMPACT = _Metrics(32, 2, 26, 10, 10, 10, 7, 13, 1)
_EXPORT_SCALE = 2
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\yugothm.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
)
_FONT_BOLD_CANDIDATES = (
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\yugothb.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
)

_REF_COLOR = "#E53935"
_COOR_COLOR = "#1E88E5"
_DISABLED_BG = "#9E9E9E"
_UNKNOWN_BG = "#90A4AE"
_TOOL_FG = "#10343C"

_TOOL_COLORS = {
    "画像取込": "#1E88E5",
    "画像+図形参照表示": "#1E88E5",
    "画像・図形参照表示": "#1E88E5",
    "位置決め": "#43A047",
    "クリップ": "#FB8C00",
"位置決め(GF)":"#43A047",
"RobotFinder":"#43A047",
"マルチ座標系":"#43A047",
"動的マルチ座標系":"#43A047",
"方向・有無検査":"#4DD0E1",
"RotationFinder":"#4DD0E1",
"IF分岐":"#FFFF00",
"ELSE":"#FF80FF",
"ENDIF":"#FF80FF",
"タスク処理中断":"#FF80FF",
"カウンタ更新キャンセル":"#FF80FF",
"接点途中出力":"#FF80FF",
"シリアル途中出力":"#FF80FF",
"処理結果出力演算":"#FF80FF",
"コネクタリード検査":"#4DD0E1",
"コネクタリード分割検査":"#4DD0E1",
"コネクタリード基準":"#4DD0E1",
"コネクタリード検査II":"#4DD0E1",
"3D-コネクタ検査":"#4DD0E1",
"3D-コネクタコプラナリティ検査":"#4DD0E1",
"ICリード検査":"#4DD0E1",
"3D-SOPリード検査":"#4DD0E1",
"3D-QFPリード検査":"#4DD0E1",
"リード曲がり検査":"#4DD0E1",
"ダムバー検査":"#4DD0E1",
"BGA検査":"#4DD0E1",
"3D-BGA検査":"#4DD0E1",
"パッケージ検出・検査":"#4DD0E1",
"パッケージ角検出":"#4DD0E1",
"文字検査":"#C8FFC8",
"OCV":"#C8FFC8",
"太陽電池欠陥検査":"#4DD0E1",
"セル検出・検査":"#4DD0E1",
"個数検査":"#4DD0E1",
"SealingInspect":"#4DD0E1",
"3D-ボンディングワイヤ検査":"#4DD0E1",
"ワイヤ検出・検査":"#4DD0E1",
"AI-DefFinder":"#4DD0E1",
"DefFinderブロブ検査":"#4DD0E1",
"DefFinder":"#4DD0E1",
"位置決め+DF+ブロブ検査":"#4DD0E1",
"TSCDefFinderブロブ検査":"#4DD0E1",
"パターン検査":"#4DD0E1",
"ブロブ検査":"#4DD0E1",
"明るさチェック":"#4DD0E1",
"傷/異物検査":"#4DD0E1",
"CrackFinder":"#4DD0E1",
"マルチリニアエッジ検査":"#4DD0E1",
"マルチ輪郭形状検査":"#4DD0E1",
"トラッキングエッジ検査":"#4DD0E1",
"SuperDefFinder":"#4DD0E1",
"MatrixDefFinder":"#4DD0E1",
"SegmentDefFinder":"#4DD0E1",
"エッジ検出・検査":"#C8FFC8",
"円検出・検査":"#C8FFC8",
"直線検出":"#C8FFC8",
"計測検出":"#C8FFC8",
"計測編集":"#C8FFC8",
"計測演算":"#C8FFC8",
"3D高さ計測・検査":"#C8FFC8",
"画像フィルタ":"#FB8C00",
"クリップ":"#FB8C00",
"画像間演算":"#FB8C00",
"RGB合成":"#FB8C00",
"PMS生成":"#FB8C00",
"画像連結":"#FB8C00",
"非線形画像変換":"#FB8C00",
"3D画像生成(合焦法)":"#FB8C00",
"2Dコード読取II":"#FF80FF",
"2Dコード読取III":"#FF80FF",
"カラー変換":"#4DD0E1",
"カラー抽出":"#4DD0E1",
"カラー位置決め":"#4DD0E1",
"カラー識別":"#4DD0E1",
"マスク":"#FB8C00",
"時間待ち":"#FF80FF",
"分配処理":"#FF80FF",
"AI分類":"#4DD0E1",
"AI-AnomalyFinder":"#4DD0E1",
}


@dataclass
class _Box:
    left: float
    top: float
    height: float = _CELL_H
    v_gap: float = _V_GAP

    @property
    def right(self) -> float:
        return self.left + _CELL_W

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def mid_y(self) -> float:
        return self.top + self.height / 2

    @property
    def gap_y(self) -> float:
        return self.bottom + self.v_gap / 2


@dataclass
class _Segment:
    kind: str
    points: list[tuple[float, float]]


@dataclass
class _ArrowHead:
    kind: str
    tip: tuple[float, float]
    direction: tuple[float, float]


def build_tool_layout_dialog(
    layout: ToolLayout,
    *,
    page: ft.Page,
    title: str,
    on_close,
    on_save,
    width: float,
    height: float,
) -> ft.AlertDialog:
    """スクロールできるツール構成ダイアログを作る。"""
    state = {
        "full": False,
        "compact": False,
        "prev_full": bool(getattr(page.window, "full_screen", False)),
    }
    grid_row = ft.Row(
        scroll=ft.ScrollMode.AUTO,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[_build_grid(layout, _NORMAL)],
    )
    content_box = ft.Container(width=width, height=height)
    compact_btn = ft.TextButton("行を圧縮", icon=ft.Icons.DENSITY_SMALL)
    full_btn = ft.TextButton("全画面", icon=ft.Icons.FULLSCREEN)
    dialog: ft.AlertDialog | None = None

    def _mode_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            padding=ft.Padding.symmetric(horizontal=8, vertical=0),
            bgcolor=ft.Colors.BLUE_50 if active else None,
            color=ft.Colors.BLUE_800 if active else None,
        )

    def _apply_mode() -> None:
        metrics = _COMPACT if state["compact"] else _NORMAL
        grid_row.controls = [_build_grid(layout, metrics)]
        compact_btn.text = "通常の行高" if state["compact"] else "行を圧縮"
        compact_btn.icon = (
            ft.Icons.DENSITY_MEDIUM if state["compact"] else ft.Icons.DENSITY_SMALL
        )
        compact_btn.style = _mode_style(state["compact"])
        full_btn.text = "全画面を解除" if state["full"] else "全画面"
        full_btn.icon = (
            ft.Icons.FULLSCREEN_EXIT if state["full"] else ft.Icons.FULLSCREEN
        )
        full_btn.style = _mode_style(state["full"])
        if state["full"]:
            page_w = float(page.width or width + 80)
            page_h = float(page.height or height + 160)
            content_box.width = max(480.0, page_w - 32)
            content_box.height = max(280.0, page_h - 150)
        else:
            content_box.width = width
            content_box.height = height

    def _toggle_compact(_e) -> None:
        state["compact"] = not state["compact"]
        _apply_mode()
        grid_row.update()
        compact_btn.update()

    async def _toggle_full() -> None:
        state["full"] = not state["full"]
        try:
            page.window.full_screen = state["full"] or state["prev_full"]
        except Exception:
            pass
        page.update()
        await asyncio.sleep(0.2)
        _apply_mode()
        if dialog is not None:
            dialog.inset_padding = ft.Padding.all(8) if state["full"] else None
            dialog.update()
        content_box.update()
        full_btn.update()

    def _on_full(_e) -> None:
        page.run_task(_toggle_full)

    def _close(_e) -> None:
        if state["full"] and not state["prev_full"]:
            try:
                page.window.full_screen = False
            except Exception:
                pass
            page.update()
        on_close(_e)

    def _save(_e) -> None:
        on_save(state["compact"])

    compact_btn.on_click = _toggle_compact
    compact_btn.style = _mode_style(False)
    full_btn.on_click = _on_full
    full_btn.style = _mode_style(False)
    content_box.content = ft.Column(
        [
            ft.Row(
                [
                    ft.Text(
                        "赤は画像参照、青は座標系。グレーの×は実行されないツール。",
                        size=11,
                        color=ft.Colors.GREY_700,
                        expand=True,
                    ),
                    compact_btn,
                    full_btn,
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[grid_row],
            ),
        ],
        expand=True,
        spacing=8,
    )
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title, size=16, weight=ft.FontWeight.W_600),
        content=content_box,
        actions=[
            ft.TextButton(
                "画像として保存",
                icon=ft.Icons.IMAGE,
                on_click=_save,
            ),
            ft.TextButton("閉じる", on_click=_close),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    return dialog


def render_tool_layout_png(
    path: str,
    layout: ToolLayout,
    *,
    title: str,
    compact: bool = False,
) -> None:
    """ツール構成全体を PNG に書き出す。compact のときは画面の圧縮行と同じ寸法。"""
    metrics = _COMPACT if compact else _NORMAL
    image = _render_tool_layout_image(layout, title=title, metrics=metrics)
    image.save(path, "PNG")


def _build_grid(layout: ToolLayout, metrics: _Metrics = _NORMAL) -> ft.Control:
    cameras = layout.cameras
    max_row = layout.max_row
    if not cameras or max_row <= 0:
        return ft.Text("ツールがありません。", size=13)
    rails = _prepare_rails(layout)
    slot_w = _CELL_W + rails.gutter
    slot_h = metrics.cell_h + metrics.v_gap
    total_w = _PAD * 2 + _ROW_HEADER_W + len(cameras) * slot_w
    total_h = _PAD * 2 + metrics.col_header_h + max_row * slot_h
    boxes = {
        (tool.camera, tool.row): _box_for(cameras, tool.camera, tool.row, metrics, slot_w)
        for tool in layout.tools
    }
    controls: list[ft.Control] = [
        _build_canvas(
            total_w,
            total_h,
            _arrow_shapes(layout, boxes, metrics.lane_offset, rails),
        ),
        _header_cell(
            _PAD, _PAD, _ROW_HEADER_W, metrics.col_header_h, "",
            size=metrics.header_size,
        ),
    ]
    for index, camera in enumerate(cameras):
        left = _PAD + _ROW_HEADER_W + index * slot_w
        controls.append(
            _header_cell(
                left, _PAD, _CELL_W, metrics.col_header_h,
                _camera_label(camera),
                size=metrics.header_size,
            )
        )
    by_pos = {(tool.camera, tool.row): tool for tool in layout.tools}
    for row in range(1, max_row + 1):
        top = _PAD + metrics.col_header_h + (row - 1) * slot_h
        controls.append(
            _header_cell(
                _PAD, top, _ROW_HEADER_W, metrics.cell_h, str(row),
                size=metrics.header_size,
            )
        )
        for index, camera in enumerate(cameras):
            left = _PAD + _ROW_HEADER_W + index * slot_w
            tool = by_pos.get((camera.number, row))
            controls.append(_tool_cell(left, top, tool, metrics))
    return ft.Stack(controls=controls, width=total_w, height=total_h)


def _box_for(
    cameras: list[CameraColumn],
    camera: int,
    row: int,
    metrics: _Metrics = _NORMAL,
    slot_w: float = _SLOT_W,
) -> _Box:
    index = next(i for i, item in enumerate(cameras) if item.number == camera)
    slot_h = metrics.cell_h + metrics.v_gap
    return _Box(
        left=_PAD + _ROW_HEADER_W + index * slot_w,
        top=_PAD + metrics.col_header_h + (row - 1) * slot_h,
        height=metrics.cell_h,
        v_gap=metrics.v_gap,
    )


def _camera_label(camera: CameraColumn) -> str:
    label = f"[ {camera.number} ]"
    if camera.title:
        return f"{label} {camera.title}"
    return label


def _header_cell(left, top, width, height, text: str, *, size: int = 12) -> ft.Container:
    return ft.Container(
        left=left,
        top=top,
        width=width,
        height=height,
        alignment=ft.Alignment(0, 0),
        bgcolor="#E8EAED",
        border=ft.Border.all(1, ft.Colors.GREY_400),
        content=ft.Text(
            text,
            size=size,
            weight=ft.FontWeight.W_600,
            text_align=ft.TextAlign.CENTER,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
    )


def _white_edge() -> ft.TextStyle:
    """暗い文字の周囲に白い縁を付けて、明るい背景でも読めるようにする。"""
    return ft.TextStyle(
        shadow=ft.BoxShadow(
            blur_radius=0.6,
            spread_radius=0.4,
            color="#FFFFFF",
            offset=ft.Offset(0, 0),
        ),
    )


def _tool_cell(
    left: float,
    top: float,
    tool: ToolCell | None,
    metrics: _Metrics = _NORMAL,
) -> ft.Container:
    if tool is None:
        return ft.Container(
            left=left,
            top=top,
            width=_CELL_W,
            height=metrics.cell_h,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, ft.Colors.GREY_300),
        )
    bg = _DISABLED_BG if not tool.enabled else _TOOL_COLORS.get(tool.tool_name, _UNKNOWN_BG)
    name = ft.Text(
        tool.tool_name,
        size=metrics.name_size,
        weight=ft.FontWeight.W_700,
        color=_TOOL_FG,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
        style=_white_edge(),
    )
    comment = ft.Text(
        tool.comment,
        size=metrics.comment_size,
        weight=ft.FontWeight.W_700,
        color=_TOOL_FG,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
        style=_white_edge(),
    )
    body = ft.Column([name, comment], spacing=0, expand=True)
    if tool.enabled:
        content = body
    else:
        content = ft.Row(
            [
                ft.Text(
                    "×",
                    size=metrics.mark_size,
                    weight=ft.FontWeight.BOLD,
                    color="#E53935",
                ),
                body,
            ],
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.Container(
        left=left,
        top=top,
        width=_CELL_W,
        height=metrics.cell_h,
        bgcolor=bg,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.25, ft.Colors.BLACK)),
        padding=ft.Padding.symmetric(horizontal=6, vertical=metrics.pad_y),
        content=content,
    )


def _build_canvas(width: float, height: float, shapes: list) -> cv.Canvas:
    return cv.Canvas(
        shapes=shapes,
        width=width,
        height=height,
        left=0,
        top=0,
    )


def _arrow_shapes(
    layout: ToolLayout,
    boxes: dict[tuple[int, int], _Box],
    lane_offset: float = _LANE_OFFSET,
    rails: _Rails | None = None,
) -> list:
    shapes = []
    for kind, segments, heads in _arrow_figures(layout, boxes, lane_offset, rails):
        color = _REF_COLOR if kind == "ref" else _COOR_COLOR
        for segment in segments:
            if len(segment.points) < 2:
                continue
            elements: list[cv.Path.PathElement] = [
                cv.Path.MoveTo(segment.points[0][0], segment.points[0][1])
            ]
            for x, y in segment.points[1:]:
                elements.append(cv.Path.LineTo(x, y))
            shapes.append(
                cv.Path(
                    elements=elements,
                    paint=ft.Paint(
                        color=color,
                        stroke_width=1.8,
                        style=ft.PaintingStyle.STROKE,
                        stroke_cap=ft.StrokeCap.ROUND,
                        stroke_join=ft.StrokeJoin.ROUND,
                    ),
                )
            )
        for head in heads:
            triangle = _arrow_triangle(head.tip, head.direction)
            shapes.append(
                cv.Path(
                    elements=[
                        cv.Path.MoveTo(triangle[0][0], triangle[0][1]),
                        cv.Path.LineTo(triangle[1][0], triangle[1][1]),
                        cv.Path.LineTo(triangle[2][0], triangle[2][1]),
                        cv.Path.Close(),
                    ],
                    paint=ft.Paint(color=color, style=ft.PaintingStyle.FILL),
                )
            )
    return shapes


@dataclass(frozen=True)
class _Rails:
    """列の右側で、重なる矢印を横にずらすための通り道。"""

    gutter: float
    ref_base: float
    coor_base: float
    pitch: float
    lanes: dict[tuple[tuple[str, int, int], int], int]


def _attach_y(
    box: _Box,
    kind: str,
    lane_offset: float = _LANE_OFFSET,
    *,
    secondary: bool = False,
) -> float:
    if kind == "ref":
        y = box.mid_y - lane_offset
        if secondary:
            y += min(8.0, max(5.0, lane_offset * 0.75))
    else:
        y = box.mid_y + lane_offset
        if secondary:
            y -= min(8.0, max(5.0, lane_offset * 0.75))
    margin = _ARROW_HALF + 1
    return min(box.bottom - margin, max(box.top + margin, y))


def _logical_attach(row: int, *, secondary: bool) -> float:
    return row + (0.4 if secondary else 0.0)


def _link_groups(layout: ToolLayout) -> dict[tuple[str, int, int], list[ToolCell]]:
    positions = {(tool.camera, tool.row) for tool in layout.tools}
    groups: dict[tuple[str, int, int], list[ToolCell]] = {}
    for tool in layout.tools:
        for kind, link in (("ref", tool.ref), ("coor", tool.coor)):
            if link is None or (link.camera, link.row) not in positions:
                continue
            groups.setdefault((kind, link.camera, link.row), []).append(tool)
    return groups


def _prepare_rails(layout: ToolLayout) -> _Rails:
    """縦の範囲が重なる同じ色の矢印に、別の通り道を割り当てる。"""
    groups = _link_groups(layout)
    spans: dict[tuple[str, int], list[tuple[float, float, tuple[str, int, int]]]] = {}
    for (kind, camera, row), consumers in groups.items():
        group_key = (kind, camera, row)
        ys = [float(row)]
        for item in consumers:
            secondary = (kind, item.camera, item.row) in groups
            if item.camera == camera:
                ys.append(_logical_attach(item.row, secondary=secondary))
                continue
            stub = _logical_attach(item.row, secondary=secondary)
            gap = item.row + 0.75
            ys.append(gap)
            _add_span(spans, kind, item.camera, stub, gap, group_key)
        _add_span(spans, kind, camera, min(ys), max(ys), group_key)
    lanes: dict[tuple[tuple[str, int, int], int], int] = {}
    max_lane = {"ref": -1, "coor": -1}
    for (kind, column), intervals in spans.items():
        for group_key, lane in _color_intervals(intervals).items():
            lanes[(group_key, column)] = lane
            max_lane[kind] = max(max_lane[kind], lane)
    has_ref = any(key[0] == "ref" for key in groups)
    has_coor = any(key[0] == "coor" for key in groups)
    ref_count = (max_lane["ref"] + 1) if max_lane["ref"] >= 0 else (1 if has_ref else 0)
    coor_count = (max_lane["coor"] + 1) if max_lane["coor"] >= 0 else (1 if has_coor else 0)
    if ref_count <= 1 and coor_count <= 1:
        return _Rails(_GUTTER, _REF_RAIL, _COOR_RAIL, _LANE_PITCH, lanes)
    ref_base = _REF_RAIL
    if ref_count == 0:
        coor_base = _COOR_RAIL
    else:
        coor_base = ref_base + ref_count * _LANE_PITCH + 6
    gutter = coor_base + max(coor_count, 1) * _LANE_PITCH + 6
    return _Rails(max(_GUTTER, gutter), ref_base, coor_base, _LANE_PITCH, lanes)


def _add_span(spans, kind: str, column: int, start: float, end: float, group_key) -> None:
    if abs(end - start) <= 0.05:
        return
    spans.setdefault((kind, column), []).append((min(start, end), max(start, end), group_key))


def _color_intervals(intervals: list[tuple[float, float, tuple]]) -> dict[tuple, int]:
    merged: dict[tuple, tuple[float, float]] = {}
    for start, end, key in intervals:
        if key in merged:
            old_start, old_end = merged[key]
            merged[key] = (min(old_start, start), max(old_end, end))
        else:
            merged[key] = (start, end)
    assigned: list[tuple[float, float, tuple, int]] = []
    lanes: dict[tuple, int] = {}
    for key, (start, end) in sorted(merged.items(), key=lambda item: (item[1][0], item[1][1])):
        used = {
            lane
            for other_start, other_end, _other, lane in assigned
            if other_end >= start and other_start <= end
        }
        lane = 0
        while lane in used:
            lane += 1
        assigned.append((start, end, key, lane))
        lanes[key] = lane
    return lanes


def _rail_x(
    cell_right: float,
    kind: str,
    group_key: tuple[str, int, int],
    column: int,
    rails: _Rails,
) -> float:
    lane = rails.lanes.get((group_key, column), 0)
    base = rails.ref_base if kind == "ref" else rails.coor_base
    return cell_right + base + lane * rails.pitch


def _arrow_figures(
    layout: ToolLayout,
    boxes: dict[tuple[int, int], _Box],
    lane_offset: float = _LANE_OFFSET,
    rails: _Rails | None = None,
):
    if rails is None:
        rails = _prepare_rails(layout)
    groups = _link_groups(layout)
    figures = []
    for (kind, camera, row), consumers in groups.items():
        if (camera, row) not in boxes:
            continue
        group_key = (kind, camera, row)
        source = boxes[(camera, row)]
        source_y = _attach_y(source, kind, lane_offset)
        rail = _rail_x(source.right, kind, group_key, camera, rails)
        same = [item for item in consumers if item.camera == camera and (item.camera, item.row) in boxes]
        cross = [item for item in consumers if item.camera != camera and (item.camera, item.row) in boxes]
        ys = [source_y]
        segments: list[_Segment] = []
        heads: list[_ArrowHead] = []
        # 矢印の頭は、参照している側ではなく参照されているツールに付ける。
        segments.append(_Segment(
            kind,
            [(rail, source_y), (source.right + _ARROW_LEN, source_y)],
        ))
        heads.append(_ArrowHead(kind, (source.right, source_y), (-1, 0)))
        for item in same:
            box = boxes[(item.camera, item.row)]
            y = _attach_y(
                box, kind, lane_offset,
                secondary=(kind, item.camera, item.row) in groups,
            )
            ys.append(y)
            segments.append(_Segment(kind, [(box.right, y), (rail, y)]))
        for item in cross:
            box = boxes[(item.camera, item.row)]
            y = _attach_y(
                box, kind, lane_offset,
                secondary=(kind, item.camera, item.row) in groups,
            )
            other_rail = _rail_x(box.right, kind, group_key, item.camera, rails)
            segments.append(_Segment(kind, [(box.right, y), (other_rail, y)]))
            segments.append(_Segment(kind, [(other_rail, y), (other_rail, box.gap_y)]))
            segments.append(_Segment(kind, [(other_rail, box.gap_y), (rail, box.gap_y)]))
            ys.append(box.gap_y)
        if max(ys) - min(ys) > 0.5:
            segments.append(_Segment(kind, [(rail, min(ys)), (rail, max(ys))]))
        figures.append((kind, segments, heads))
    return figures


def _render_tool_layout_image(
    layout: ToolLayout,
    *,
    title: str,
    metrics: _Metrics = _NORMAL,
) -> Image.Image:
    grid = _render_grid_image(layout, metrics)
    scale = _EXPORT_SCALE
    header_h = 52 * scale
    image = Image.new("RGB", (grid.width, header_h + grid.height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(16 * scale)
    note_font = _load_font(11 * scale)
    draw.text((12 * scale, 8 * scale), title or "ツール構成", fill="#212121", font=title_font)
    draw.text(
        (12 * scale, 30 * scale),
        "赤は画像参照、青は座標系。グレーの×は実行されないツール。",
        fill="#616161",
        font=note_font,
    )
    image.paste(grid, (0, header_h))
    return image


def _render_grid_image(layout: ToolLayout, metrics: _Metrics = _NORMAL) -> Image.Image:
    cameras = layout.cameras
    max_row = layout.max_row
    if not cameras or max_row <= 0:
        image = Image.new("RGB", (320, 48), "#FFFFFF")
        ImageDraw.Draw(image).text((8, 12), "ツールがありません。", fill="#212121", font=_load_font(14))
        return image
    rails = _prepare_rails(layout)
    slot_w = _CELL_W + rails.gutter
    slot_h = metrics.cell_h + metrics.v_gap
    total_w = _px(_PAD * 2 + _ROW_HEADER_W + len(cameras) * slot_w)
    total_h = _px(_PAD * 2 + metrics.col_header_h + max_row * slot_h)
    image = Image.new("RGB", (total_w, total_h), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    boxes = {
        (tool.camera, tool.row): _box_for(cameras, tool.camera, tool.row, metrics, slot_w)
        for tool in layout.tools
    }
    _draw_arrows(draw, layout, boxes, metrics.lane_offset, rails)
    _draw_rect(draw, _PAD, _PAD, _ROW_HEADER_W, metrics.col_header_h, "#E8EAED", "#BDBDBD")
    name_font = _load_font(metrics.header_size * _EXPORT_SCALE)
    for index, camera in enumerate(cameras):
        left = _PAD + _ROW_HEADER_W + index * slot_w
        _draw_rect(draw, left, _PAD, _CELL_W, metrics.col_header_h, "#E8EAED", "#BDBDBD")
        _draw_centered_text(
            draw, left, _PAD, _CELL_W, metrics.col_header_h,
            _camera_label(camera), name_font, "#212121",
        )
    by_pos = {(tool.camera, tool.row): tool for tool in layout.tools}
    row_font = _load_font(metrics.header_size * _EXPORT_SCALE)
    tool_font = _load_font(metrics.name_size * _EXPORT_SCALE, bold=True)
    comment_font = _load_font(metrics.comment_size * _EXPORT_SCALE, bold=True)
    mark_font = _load_font(metrics.mark_size * _EXPORT_SCALE, bold=True)
    for row in range(1, max_row + 1):
        top = _PAD + metrics.col_header_h + (row - 1) * slot_h
        _draw_rect(draw, _PAD, top, _ROW_HEADER_W, metrics.cell_h, "#E8EAED", "#BDBDBD")
        _draw_centered_text(
            draw, _PAD, top, _ROW_HEADER_W, metrics.cell_h, str(row), row_font, "#212121",
        )
        for index, camera in enumerate(cameras):
            left = _PAD + _ROW_HEADER_W + index * slot_w
            _draw_tool(
                draw, left, top, by_pos.get((camera.number, row)),
                tool_font, comment_font, metrics, mark_font,
            )
    return image


def _draw_arrows(
    draw: ImageDraw.ImageDraw,
    layout: ToolLayout,
    boxes: dict[tuple[int, int], _Box],
    lane_offset: float = _LANE_OFFSET,
    rails: _Rails | None = None,
) -> None:
    for kind, segments, heads in _arrow_figures(layout, boxes, lane_offset, rails):
        color = _REF_COLOR if kind == "ref" else _COOR_COLOR
        width = max(2, _px(1.8))
        for segment in segments:
            if len(segment.points) < 2:
                continue
            points = [(_px(x), _px(y)) for x, y in segment.points]
            draw.line(points, fill=color, width=width)
        for head in heads:
            triangle = [(_px(x), _px(y)) for x, y in _arrow_triangle(head.tip, head.direction)]
            draw.polygon(triangle, fill=color)


def _draw_tool(
    draw,
    left,
    top,
    tool: ToolCell | None,
    tool_font,
    comment_font,
    metrics: _Metrics = _NORMAL,
    mark_font=None,
) -> None:
    if tool is None:
        _draw_rect(draw, left, top, _CELL_W, metrics.cell_h, "#FFFFFF", "#E0E0E0")
        return
    bg = _DISABLED_BG if not tool.enabled else _TOOL_COLORS.get(tool.tool_name, _UNKNOWN_BG)
    _draw_rect(draw, left, top, _CELL_W, metrics.cell_h, bg, "#9E9E9E")
    pad = 6
    text_left = left + pad
    text_width = _CELL_W - pad * 2
    if metrics.cell_h >= _CELL_H:
        name_dy, comment_dy, mark_dy = 4, 22, 10
    else:
        name_dy = metrics.pad_y + 1
        comment_dy = name_dy + metrics.name_size + 3
        mark_dy = max(0, (metrics.cell_h - metrics.mark_size) / 2)
    if not tool.enabled:
        mark = "×"
        mark_font = mark_font or tool_font
        draw.text((_px(text_left), _px(top + mark_dy)), mark, fill="#E53935", font=mark_font)
        mark_w = draw.textlength(mark, font=mark_font) / _EXPORT_SCALE
        text_left += mark_w + 4
        text_width = left + _CELL_W - pad - text_left
    name = _fit_text(draw, tool.tool_name, tool_font, _px(max(8, text_width)))
    comment = _fit_text(draw, tool.comment, comment_font, _px(max(8, text_width)))
    draw.text(
        (_px(text_left), _px(top + name_dy)),
        name,
        fill=_TOOL_FG,
        font=tool_font,
        stroke_width=2,
        stroke_fill="#FFFFFF",
    )
    draw.text(
        (_px(text_left), _px(top + comment_dy)),
        comment,
        fill=_TOOL_FG,
        font=comment_font,
        stroke_width=2,
        stroke_fill="#FFFFFF",
    )


def _draw_rect(draw, left, top, width, height, fill: str, outline: str) -> None:
    x0, y0 = _px(left), _px(top)
    x1, y1 = _px(left + width), _px(top + height)
    draw.rectangle((x0, y0, x1, y1), fill=fill, outline=outline)


def _draw_centered_text(draw, left, top, width, height, text: str, font, fill: str) -> None:
    fitted = _fit_text(draw, text, font, _px(width - 8))
    text_w = draw.textlength(fitted, font=font)
    bbox = font.getbbox(fitted)
    text_h = bbox[3] - bbox[1]
    x = _px(left) + (_px(width) - text_w) / 2
    y = _px(top) + (_px(height) - text_h) / 2 - bbox[1]
    draw.text((x, y), fitted, fill=fill, font=font)


def _fit_text(draw, text: str, font, max_width: float) -> str:
    if not text or draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and draw.textlength(trimmed + ellipsis, font=font) > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed}{ellipsis}" if trimmed else ellipsis


def _px(value: float) -> int:
    return int(round(value * _EXPORT_SCALE))


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = _FONT_BOLD_CANDIDATES if bold else _FONT_CANDIDATES
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    if bold:
        return _load_font(size)
    return ImageFont.load_default()


def _arrow_triangle(tip: tuple[float, float], direction: tuple[float, float]):
    dx, dy = direction
    px, py = -dy, dx
    base_x = tip[0] - dx * _ARROW_LEN
    base_y = tip[1] - dy * _ARROW_LEN
    return [
        tip,
        (base_x + px * _ARROW_HALF, base_y + py * _ARROW_HALF),
        (base_x - px * _ARROW_HALF, base_y - py * _ARROW_HALF),
    ]
