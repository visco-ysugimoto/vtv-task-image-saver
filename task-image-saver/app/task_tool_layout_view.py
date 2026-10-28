"""ツール構成をカメラ列×行のグリッドとして描く。"""
from __future__ import annotations

import asyncio
import os
import re
import struct
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

# キーは VTV 日本語のツール名。英語・韓国語・中国語は同じ文字列 ID の名前へ同じ色を付ける。
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

_JP_LANG = 0x411
_LANG_IDS = {"ja": 0x411, "en": 0x409, "ko": 0x412, "zh": 0x804}
_LANG_LABELS = {"ja": "日本語", "en": "英語", "ko": "韓国語", "zh": "中国語"}
_NAME_ALIASES: dict[str, str] = {}
_NAME_FORMS: dict[str, dict[str, str]] = {}
_ALIAS_DLL: str | None = None
_ALIAS_READY = False
_COMMENT_INDEX_RE = re.compile(r"\d{2}(?!\d)")


def use_tool_name_catalog(hint_path: str | None = None) -> None:
    """vxaCommon.dll から、色表の日本語名に対応する他言語のツール名を読む。"""
    global _ALIAS_DLL, _ALIAS_READY, _NAME_ALIASES, _NAME_FORMS
    dll = _find_vxa_common(hint_path)
    if _ALIAS_READY and dll == _ALIAS_DLL:
        return
    _ALIAS_DLL = dll
    _ALIAS_READY = True
    if dll:
        _NAME_ALIASES, _NAME_FORMS = _load_name_catalog(dll)
    else:
        _NAME_ALIASES = {}
        _NAME_FORMS = {}


def _color_key(name: str) -> str | None:
    """色表のキーへ揃える。VTV は括弧が全角のことがある。"""
    if name in _TOOL_COLORS:
        return name
    folded = name.replace("（", "(").replace("）", ")")
    if folded in _TOOL_COLORS:
        return folded
    dotted = folded.replace("・", "+")
    if dotted in _TOOL_COLORS:
        return dotted
    return None


def _tool_color(name: str) -> str:
    key = _color_key(name)
    if key:
        return _TOOL_COLORS[key]
    if not _ALIAS_READY:
        use_tool_name_catalog(None)
    key = _NAME_ALIASES.get(name) or _NAME_ALIASES.get(
        name.replace("（", "(").replace("）", ")")
    )
    if not key:
        return _UNKNOWN_BG
    return _TOOL_COLORS.get(key, _UNKNOWN_BG)


def _find_vxa_common(hint_path: str | None) -> str | None:
    roots: list[str] = []
    if hint_path:
        current = os.path.abspath(hint_path)
        for _ in range(8):
            roots.append(current)
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    roots.append(r"C:\viscotech")
    seen: set[str] = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        path = os.path.join(root, "bin", "vxaCommon.dll")
        if os.path.isfile(path):
            return path
    return None


def _is_name_label(text: str) -> bool:
    if not text or len(text) > 48:
        return False
    return not any(ch in text for ch in "\r\n%{}\\")


def _index_keys(text: str) -> list[str]:
    keys = [text]
    folded = text.replace("（", "(").replace("）", ")")
    if folded not in keys:
        keys.append(folded)
    dotted = folded.replace("・", "+")
    if dotted not in keys:
        keys.append(dotted)
    return keys


def _load_name_catalog(path: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    try:
        tables = _pe_string_tables(path, tuple(_LANG_IDS.values()))
    except OSError:
        return {}, {}
    candidates: list[dict[str, str]] = []
    for sid, jp_raw in tables.get(_JP_LANG, {}).items():
        jp_name = jp_raw.strip()
        if not _is_name_label(jp_name):
            continue
        forms = {"ja": jp_name}
        for code, lang_id in _LANG_IDS.items():
            if code == "ja":
                continue
            foreign = tables.get(lang_id, {}).get(sid, "").strip()
            if _is_name_label(foreign):
                forms[code] = foreign
        if len(set(forms.values())) < 2 and _color_key(jp_name) is None:
            continue
        candidates.append(forms)
    candidates.sort(key=lambda forms: _color_key(forms["ja"]) is None)
    forms_index: dict[str, dict[str, str]] = {}
    for forms in candidates:
        for text in forms.values():
            for key in _index_keys(text):
                forms_index.setdefault(key, forms)
    grouped: dict[str, set[str]] = {}
    for forms in candidates:
        key = _color_key(forms["ja"])
        if key is None:
            continue
        for code, text in forms.items():
            if code == "ja" or text == key:
                continue
            for alias in _index_keys(text):
                grouped.setdefault(alias, set()).add(key)
    aliases: dict[str, str] = {}
    for foreign, jp_names in grouped.items():
        colors = {_TOOL_COLORS[name] for name in jp_names}
        if len(colors) == 1:
            aliases[foreign] = next(iter(jp_names))
    return aliases, forms_index


def _forms_for(name: str) -> dict[str, str] | None:
    if not _ALIAS_READY:
        use_tool_name_catalog(None)
    forms = _NAME_FORMS.get(name)
    if forms is not None:
        return forms
    folded = name.replace("（", "(").replace("）", ")")
    return _NAME_FORMS.get(folded)


def tool_name_in(name: str, lang: str) -> str:
    """ツール種別名を指定言語の表記にする。見つからなければ元の文字列。"""
    forms = _forms_for(name)
    if not forms:
        return name
    if lang == "ja":
        ja_name = forms.get("ja", "")
        if name.replace("（", "(").replace("）", ")") == ja_name.replace("（", "(").replace("）", ")"):
            return name
    return forms.get(lang) or name


def _comment_stem(comment: str) -> str:
    match = _COMMENT_INDEX_RE.search(comment or "")
    if match is None:
        return (comment or "").strip()
    return (comment or "")[:match.start()].rstrip(" _")


def detect_tool_name_language(layout: ToolLayout) -> str:
    """コメントの既定名から、タスクを作ったときのツール名の言語を推定する。"""
    if not _ALIAS_READY:
        use_tool_name_catalog(None)
    scores: dict[str, int] = {}
    for tool in layout.tools:
        forms = _forms_for(tool.tool_name)
        if not forms:
            continue
        stem = _comment_stem(tool.comment)
        if not stem:
            continue
        for lang, text in forms.items():
            if stem == text or stem.replace("（", "(").replace("）", ")") == text.replace("（", "(").replace("）", ")"):
                scores[lang] = scores.get(lang, 0) + 1
                break
    if not scores:
        return "ja"
    best = max(scores, key=lambda lang: (scores[lang], lang != "ja"))
    if best != "ja" and scores[best] > scores.get("ja", 0):
        return best
    return "ja"


def _pe_string_tables(path: str, langs: tuple[int, ...]) -> dict[int, dict[int, str]]:
    """PE の STRINGTABLE を言語ごとに {文字列 ID: 本文} で返す。"""
    data = open(path, "rb").read()
    if data[:2] != b"MZ":
        return {}
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\x00\x00":
        return {}
    magic = struct.unpack_from("<H", data, pe + 24)[0]
    dd_off = pe + 24 + (112 if magic == 0x20B else 96)
    res_rva = struct.unpack_from("<I", data, dd_off + 16)[0]
    if not res_rva:
        return {}
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    sec_off = pe + 24 + opt_size
    sections = []
    for index in range(nsec):
        off = sec_off + index * 40
        va, raw_size, raw_ptr = struct.unpack_from("<III", data, off + 12)
        sections.append((va, raw_size, raw_ptr))

    def rva_to_off(rva: int) -> int | None:
        for va, raw_size, raw_ptr in sections:
            if va <= rva < va + max(raw_size, 1):
                return raw_ptr + (rva - va)
        return None

    wanted = set(langs)
    tables: dict[int, dict[int, str]] = {lang: {} for lang in wanted}

    def walk(rel: int, path_ids: tuple[int, ...]):
        off = rva_to_off(res_rva + rel)
        if off is None:
            return
        named, count = struct.unpack_from("<HH", data, off + 12)
        entry = off + 16
        for index in range(named + count):
            ident, child = struct.unpack_from("<II", data, entry + index * 8)
            if ident & 0x80000000:
                continue
            key = path_ids + (ident,)
            if child & 0x80000000:
                walk(child & 0x7FFFFFFF, key)
                continue
            if not key or key[0] != 6 or len(key) < 3 or key[2] not in wanted:
                continue
            data_off = rva_to_off(res_rva + child)
            if data_off is None:
                continue
            blob_rva, size = struct.unpack_from("<II", data, data_off)
            raw = rva_to_off(blob_rva)
            if raw is None:
                continue
            blob = data[raw:raw + size]
            pos = 0
            base = (key[1] - 1) * 16
            for slot in range(16):
                if pos + 2 > len(blob):
                    break
                length = struct.unpack_from("<H", blob, pos)[0]
                pos += 2
                text = blob[pos:pos + length * 2].decode("utf-16le", "replace")
                pos += length * 2
                if text:
                    tables[key[2]][base + slot] = text

    walk(0, ())
    return tables


@dataclass
class _Box:
    left: float
    top: float
    height: float = _CELL_H
    v_gap: float = _V_GAP
    width: float = _CELL_W

    @property
    def right(self) -> float:
        return self.left + self.width

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
    on_save_excel,
    width: float,
    height: float,
) -> ft.AlertDialog:
    """スクロールできるツール構成ダイアログを作る。"""
    origin = detect_tool_name_language(layout)
    state = {
        "full": False,
        "compact": False,
        "prev_full": bool(getattr(page.window, "full_screen", False)),
        "origin": origin,
        "lang": origin,
    }
    grid_row = ft.Row(
        scroll=ft.ScrollMode.AUTO,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[_build_grid(layout, _NORMAL, state["lang"])],
    )
    content_box = ft.Container(width=width, height=height)
    compact_btn = ft.TextButton("行を圧縮", icon=ft.Icons.DENSITY_SMALL)
    full_btn = ft.TextButton("全画面", icon=ft.Icons.FULLSCREEN)
    lang_btn = ft.TextButton("日本語で表示", icon=ft.Icons.TRANSLATE)
    dialog: ft.AlertDialog | None = None

    def _mode_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            padding=ft.Padding.symmetric(horizontal=8, vertical=0),
            bgcolor=ft.Colors.BLUE_50 if active else None,
            color=ft.Colors.BLUE_800 if active else None,
        )

    def _apply_mode() -> None:
        metrics = _COMPACT if state["compact"] else _NORMAL
        grid_row.controls = [_build_grid(layout, metrics, state["lang"])]
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
        origin_label = _LANG_LABELS.get(state["origin"], "元の言語")
        if state["lang"] == "ja":
            lang_btn.text = f"{origin_label}で表示"
        else:
            lang_btn.text = "日本語で表示"
        lang_btn.style = _mode_style(state["lang"] == "ja")
        if state["full"]:
            page_w = float(page.width or width + 80)
            page_h = float(page.height or height + 160)
            content_box.width = max(480.0, page_w - 32)
            content_box.height = max(280.0, page_h - 150)
        else:
            content_box.width = width
            content_box.height = height

    def _toggle_lang(_e) -> None:
        state["lang"] = state["origin"] if state["lang"] == "ja" else "ja"
        _apply_mode()
        grid_row.update()
        lang_btn.update()

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
        on_save(state["compact"], state["lang"])

    def _save_excel(_e) -> None:
        on_save_excel(state["lang"])

    compact_btn.on_click = _toggle_compact
    compact_btn.style = _mode_style(False)
    full_btn.on_click = _on_full
    full_btn.style = _mode_style(False)
    lang_btn.on_click = _toggle_lang
    lang_btn.visible = origin != "ja"
    _apply_mode()
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
                    lang_btn,
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
            ft.TextButton(
                "Excelとして保存",
                icon=ft.Icons.TABLE_CHART,
                on_click=_save_excel,
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
    name_lang: str = "ja",
) -> None:
    """ツール構成全体を PNG に書き出す。compact のときは画面の圧縮行と同じ寸法。"""
    metrics = _COMPACT if compact else _NORMAL
    image = _render_tool_layout_image(
        layout, title=title, metrics=metrics, name_lang=name_lang,
    )
    image.save(path, "PNG")


def render_tool_layout_xlsx(
    path: str,
    layout: ToolLayout,
    *,
    title: str,
    name_lang: str = "ja",
) -> None:
    """ツール構成を Excel ブックに書き出す。矢印はセルに追従する線図形にする。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.page import PageMargins

    book = Workbook()
    grid = book.active
    grid.title = "ツール構成"
    drawing = _write_layout_grid(
        grid, layout, title=title, styles=(Alignment, Border, Font, PatternFill, Side),
        name_lang=name_lang,
    )
    listing = book.create_sheet("一覧")
    _write_layout_list(
        listing, layout, styles=(Alignment, Border, Font, PatternFill, Side),
        name_lang=name_lang,
    )
    for sheet in (grid, listing):
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5)
        sheet.oddHeader.left.text = title or "ツール構成"
    book.save(path)
    if drawing:
        _embed_excel_drawing(path, drawing)


def _write_layout_grid(sheet, layout: ToolLayout, *, title: str, styles, name_lang: str = "ja") -> str | None:
    from openpyxl.utils import get_column_letter

    Alignment, Border, Font, PatternFill, Side = styles
    cameras = layout.cameras
    rails = _prepare_rails(layout)
    label_width = 8
    tool_width = 30
    gutter_width = _col_width_from_px(rails.gutter + 10)
    columns = 1 + max(1, len(cameras) * 2)
    thin = Side(style="thin", color="BDBDBD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="E8EAED")
    header_font = Font(name="Yu Gothic", size=11, bold=True, color="212121")
    title_font = Font(name="Yu Gothic", size=14, bold=True, color="212121")
    note_font = Font(name="Yu Gothic", size=10, color="616161")
    body_font = Font(name="Yu Gothic", size=10, color=_TOOL_FG.lstrip("#"))
    wrap = Alignment(wrap_text=True, vertical="top", horizontal="left")
    center = Alignment(wrap_text=True, vertical="center", horizontal="center")

    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    sheet["A1"] = _xlsx_text(title or "ツール構成")
    sheet["A1"].font = title_font
    sheet["A1"].alignment = Alignment(vertical="center", horizontal="left")
    sheet.row_dimensions[1].height = 24

    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=columns)
    sheet["A2"] = "赤線は画像参照、青線は座標参照。×は実行されないツール。線はセルに追従します。"
    sheet["A2"].font = note_font
    sheet.row_dimensions[2].height = 18

    corner = sheet.cell(3, 1, "行")
    corner.font = header_font
    corner.fill = header_fill
    corner.alignment = center
    corner.border = border
    for index, camera in enumerate(cameras):
        tool_col = 2 + index * 2
        gutter_col = tool_col + 1
        cell = sheet.cell(3, tool_col, _camera_label(camera))
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
        gutter = sheet.cell(3, gutter_col, "")
        gutter.fill = header_fill
        gutter.border = border
    if not cameras:
        sheet.cell(4, 1, "ツールがありません。").font = body_font
        return None

    by_pos = {(tool.camera, tool.row): tool for tool in layout.tools}
    for row in range(1, layout.max_row + 1):
        excel_row = row + 3
        label = sheet.cell(excel_row, 1, row)
        label.font = header_font
        label.fill = header_fill
        label.alignment = center
        label.border = border
        line_count = 1
        for index, camera in enumerate(cameras):
            tool_col = 2 + index * 2
            gutter_col = tool_col + 1
            tool = by_pos.get((camera.number, row))
            cell = sheet.cell(excel_row, tool_col)
            cell.border = border
            cell.alignment = wrap
            gutter = sheet.cell(excel_row, gutter_col, "")
            gutter.border = border
            gutter.fill = PatternFill("solid", fgColor="FFFFFF")
            if tool is None:
                cell.fill = PatternFill("solid", fgColor="FFFFFF")
                continue
            lines = _tool_lines(tool, name_lang)
            line_count = max(line_count, len(lines))
            cell.value = "\n".join(lines)
            cell.font = body_font
            cell.fill = PatternFill("solid", fgColor=_tool_fill(tool))
        sheet.row_dimensions[excel_row].height = max(36, 15 * line_count + 8)

    sheet.column_dimensions["A"].width = label_width
    for index in range(len(cameras)):
        tool_col = 2 + index * 2
        sheet.column_dimensions[get_column_letter(tool_col)].width = tool_width
        sheet.column_dimensions[get_column_letter(tool_col + 1)].width = gutter_width
    sheet.freeze_panes = "B4"
    sheet.print_title_rows = "1:3"
    sheet.page_setup.horizontalCentered = True
    sheet.sheet_view.showGridLines = False
    return _excel_arrow_drawing(
        sheet,
        layout,
        rails,
        label_width=label_width,
        tool_width=tool_width,
        gutter_width=gutter_width,
    )


def _write_layout_list(sheet, layout: ToolLayout, *, styles, name_lang: str = "ja") -> None:
    from openpyxl.utils import get_column_letter

    Alignment, Border, Font, PatternFill, Side = styles
    headers = ("カメラ", "行", "ツール名", "コメント", "実行", "画像参照", "座標参照")
    header_font = Font(name="Yu Gothic", size=11, bold=True, color="212121")
    header_fill = PatternFill("solid", fgColor="E8EAED")
    body_font = Font(name="Yu Gothic", size=10, color="212121")
    thin = Side(style="thin", color="E0E0E0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(vertical="center", horizontal="center")
    left = Alignment(vertical="center", horizontal="left")
    for index, header in enumerate(headers, start=1):
        cell = sheet.cell(1, index, header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    for row_index, tool in enumerate(layout.tools, start=2):
        values = (
            tool.camera,
            tool.row,
            _xlsx_text(tool_name_in(tool.tool_name, name_lang)),
            _xlsx_text(tool.comment),
            "する" if tool.enabled else "しない",
            _link_text(tool.ref),
            _link_text(tool.coor),
        )
        for index, value in enumerate(values, start=1):
            cell = sheet.cell(row_index, index, value)
            cell.font = body_font
            cell.border = border
            cell.alignment = center if index in (1, 2, 5) else left
        sheet.cell(row_index, 3).fill = PatternFill("solid", fgColor=_tool_fill(tool))
    sheet.auto_filter.ref = f"A1:G{max(1, len(layout.tools) + 1)}"
    sheet.freeze_panes = "A2"
    widths = (10, 8, 28, 28, 10, 36, 36)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.sheet_view.showGridLines = False


def _tool_lines(tool: ToolCell, name_lang: str = "ja") -> list[str]:
    name = _xlsx_text(tool_name_in(tool.tool_name, name_lang))
    if not tool.enabled:
        name = f"× {name}"
    lines = [name]
    comment = _xlsx_text(tool.comment)
    if comment:
        lines.append(comment)
    return lines


def _link_text(link) -> str:
    if link is None:
        return ""
    return f"[{link.camera}] {link.row} {_xlsx_text(link.name)}".strip()


def _tool_fill(tool: ToolCell) -> str:
    color = _DISABLED_BG if not tool.enabled else _tool_color(tool.tool_name)
    return color.lstrip("#")


def _xlsx_text(value: str) -> str:
    return "".join(
        ch for ch in (value or "")
        if ch in "\t\n\r" or ord(ch) >= 32
    )


def _px_from_col_width(width: float) -> float:
    """Excel の列幅（文字数）を、矢印位置に使うピクセルへ換算する。"""
    return int(((256 * width + int(128 / 7)) / 256) * 7)


def _col_width_from_px(pixels: float) -> float:
    width = max(3.0, (pixels - 5) / 7)
    for _ in range(6):
        got = _px_from_col_width(width)
        if abs(got - pixels) < 1:
            break
        width += (pixels - got) / 7
    return round(width, 2)


def _row_height_px(sheet, row: int) -> float:
    height = sheet.row_dimensions[row].height
    if not height:
        height = 15
    return float(height) * 96 / 72


def _excel_arrow_drawing(
    sheet,
    layout: ToolLayout,
    rails: _Rails,
    *,
    label_width: float,
    tool_width: float,
    gutter_width: float,
) -> str | None:
    """画面と同じ経路の矢印を、セル位置に結び付く線図形の XML にする。"""
    cameras = layout.cameras
    if not cameras or layout.max_row <= 0:
        return None
    label_px = _px_from_col_width(label_width)
    tool_px = _px_from_col_width(tool_width)
    gutter_px = _px_from_col_width(gutter_width)
    col_widths = [label_px]
    for _camera in cameras:
        col_widths.extend((tool_px, gutter_px))
    row_heights = [_row_height_px(sheet, row) for row in range(1, layout.max_row + 4)]
    grid = _SheetGrid(col_widths, row_heights)
    boxes: dict[tuple[int, int], _Box] = {}
    for index, camera in enumerate(cameras):
        left = label_px + index * (tool_px + gutter_px)
        for row in range(1, layout.max_row + 1):
            excel_row = row + 3
            top = sum(row_heights[:excel_row - 1])
            boxes[(camera.number, row)] = _Box(
                left=left,
                top=top,
                height=row_heights[excel_row - 1],
                v_gap=0,
                width=tool_px,
            )
    present = {(tool.camera, tool.row) for tool in layout.tools}
    boxes = {key: box for key, box in boxes.items() if key in present}
    figures = _arrow_figures(layout, boxes, _LANE_OFFSET, rails)
    anchors: list[str] = []
    shape_id = 2
    for kind, segments, heads in figures:
        color = "E53935" if kind == "ref" else "1E88E5"
        tips = {(round(head.tip[0], 1), round(head.tip[1], 1)) for head in heads}
        for segment in segments:
            if len(segment.points) < 2:
                continue
            points = _extend_arrow_shaft(segment.points, heads)
            for start, end in zip(points, points[1:]):
                if abs(start[0] - end[0]) < 0.5 and abs(start[1] - end[1]) < 0.5:
                    continue
                arrow_at_end = (round(end[0], 1), round(end[1], 1)) in tips
                arrow_at_start = (round(start[0], 1), round(start[1], 1)) in tips
                if arrow_at_start and not arrow_at_end:
                    start, end = end, start
                    arrow_at_end = True
                anchor = _connector_anchor(
                    grid, start, end, color, shape_id, arrow=arrow_at_end,
                )
                if anchor:
                    anchors.append(anchor)
                    shape_id += 1
    if not anchors:
        return None
    body = "\n".join(anchors)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">\n'
        f"{body}\n"
        "</xdr:wsDr>\n"
    )


def _extend_arrow_shaft(points, heads) -> list[tuple[float, float]]:
    updated = list(points)
    if len(updated) < 2 or abs(updated[0][1] - updated[-1][1]) > 0.5:
        return updated
    for head in heads:
        shaft = (
            head.tip[0] - head.direction[0] * _ARROW_LEN,
            head.tip[1] - head.direction[1] * _ARROW_LEN,
        )
        for index, point in enumerate(updated):
            if abs(point[0] - shaft[0]) < 1.5 and abs(point[1] - shaft[1]) < 1.5:
                updated[index] = head.tip
                return updated
    return updated


class _SheetGrid:
    def __init__(self, col_widths: list[float], row_heights: list[float]):
        self.col_edges = [0.0]
        for width in col_widths:
            self.col_edges.append(self.col_edges[-1] + width)
        self.row_edges = [0.0]
        for height in row_heights:
            self.row_edges.append(self.row_edges[-1] + height)

    def locate(self, x: float, y: float) -> tuple[int, int, int, int]:
        col = _edge_index(self.col_edges, x)
        row = _edge_index(self.row_edges, y)
        col_span = self.col_edges[col + 1] - self.col_edges[col]
        row_span = self.row_edges[row + 1] - self.row_edges[row]
        col_off = int(round((x - self.col_edges[col]) * 9525))
        row_off = int(round((y - self.row_edges[row]) * 9525))
        col_max = max(0, int(col_span * 9525) - 1)
        row_max = max(0, int(row_span * 9525) - 1)
        return col, min(col_max, max(0, col_off)), row, min(row_max, max(0, row_off))


def _edge_index(edges: list[float], value: float) -> int:
    for index in range(len(edges) - 1):
        if value < edges[index + 1] or index == len(edges) - 2:
            return index
    return len(edges) - 2


def _connector_anchor(grid: _SheetGrid, start, end, color: str, shape_id: int, *, arrow: bool) -> str:
    frm = grid.locate(*start)
    to = grid.locate(*end)
    if frm == to:
        return ""
    tip_at_to = arrow
    if not _anchor_before(frm, to):
        frm, to = to, frm
        if arrow:
            tip_at_to = not tip_at_to
    if arrow and tip_at_to:
        head = '<a:tailEnd type="triangle" w="med" len="med"/>'
    elif arrow:
        head = '<a:headEnd type="triangle" w="med" len="med"/>'
    else:
        head = ""
    c0, co0, r0, ro0 = frm
    c1, co1, r1, ro1 = to
    return (
        "<xdr:twoCellAnchor>"
        f"<xdr:from><xdr:col>{c0}</xdr:col><xdr:colOff>{co0}</xdr:colOff>"
        f"<xdr:row>{r0}</xdr:row><xdr:rowOff>{ro0}</xdr:rowOff></xdr:from>"
        f"<xdr:to><xdr:col>{c1}</xdr:col><xdr:colOff>{co1}</xdr:colOff>"
        f"<xdr:row>{r1}</xdr:row><xdr:rowOff>{ro1}</xdr:rowOff></xdr:to>"
        "<xdr:cxnSp>"
        "<xdr:nvCxnSpPr>"
        f'<xdr:cNvPr id="{shape_id}" name="Arrow {shape_id}"/>'
        "<xdr:cNvCxnSpPr/>"
        "</xdr:nvCxnSpPr>"
        "<xdr:spPr>"
        '<a:xfrm><a:off x="0" y="0"/><a:ext cx="1" cy="1"/></a:xfrm>'
        '<a:prstGeom prst="straightConnector1"><a:avLst/></a:prstGeom>'
        f'<a:ln w="19050"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>{head}</a:ln>'
        "</xdr:spPr>"
        "</xdr:cxnSp>"
        "<xdr:clientData/>"
        "</xdr:twoCellAnchor>"
    )


def _anchor_before(frm: tuple[int, int, int, int], to: tuple[int, int, int, int]) -> bool:
    if frm[2] != to[2]:
        return frm[2] < to[2]
    if frm[0] != to[0]:
        return frm[0] < to[0]
    return frm[1] <= to[1]


def _embed_excel_drawing(path: str, drawing_xml: str) -> None:
    import zipfile
    from io import BytesIO

    with zipfile.ZipFile(path, "r") as source:
        names = source.namelist()
        files = {name: source.read(name) for name in names}
    sheet_path = _grid_sheet_target(files)
    rels_path = sheet_path.replace("worksheets/", "worksheets/_rels/") + ".rels"
    drawing_path = "xl/drawings/drawing1.xml"
    rel_id = _next_rel_id(files.get(rels_path))
    files[sheet_path] = _insert_drawing_tag(files[sheet_path], rel_id)
    files[rels_path] = _insert_drawing_rel(files.get(rels_path), rel_id)
    files["[Content_Types].xml"] = _insert_drawing_content_type(files["[Content_Types].xml"])
    files[drawing_path] = drawing_xml.encode("utf-8")
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, data in files.items():
            target.writestr(name, data)
    with open(path, "wb") as handle:
        handle.write(buffer.getvalue())


def _grid_sheet_target(files: dict[str, bytes]) -> str:
    import xml.etree.ElementTree as ET

    ns = {
        "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "p": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    workbook = ET.fromstring(files["xl/workbook.xml"])
    rel_id = None
    for sheet in workbook.findall("m:sheets/m:sheet", ns):
        if sheet.attrib.get("name") == "ツール構成":
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            break
    rels = ET.fromstring(files["xl/_rels/workbook.xml.rels"])
    for rel in rels:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib["Target"].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            return target
    return "xl/worksheets/sheet1.xml"


def _next_rel_id(rels_xml: bytes | None) -> str:
    if not rels_xml:
        return "rId1"
    import xml.etree.ElementTree as ET

    root = ET.fromstring(rels_xml)
    used = []
    for rel in root:
        rel_id = rel.attrib.get("Id", "")
        if rel_id.startswith("rId") and rel_id[3:].isdigit():
            used.append(int(rel_id[3:]))
    return f"rId{max(used, default=0) + 1}"


def _insert_drawing_tag(sheet_xml: bytes, rel_id: str) -> bytes:
    text = sheet_xml.decode("utf-8")
    if "<drawing " in text:
        return sheet_xml
    if "</worksheet>" not in text:
        return sheet_xml
    relation_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    if "xmlns:r=" not in text:
        text = text.replace(
            "<worksheet ",
            f'<worksheet xmlns:r="{relation_ns}" ',
            1,
        )
    tag = f'<drawing r:id="{rel_id}"/>'
    return text.replace("</worksheet>", f"{tag}</worksheet>").encode("utf-8")


def _insert_drawing_rel(rels_xml: bytes | None, rel_id: str) -> bytes:
    rel = (
        f'<Relationship Id="{rel_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" '
        'Target="../drawings/drawing1.xml"/>'
    )
    if not rels_xml:
        xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rel}</Relationships>"
        )
        return xml.encode("utf-8")
    text = rels_xml.decode("utf-8")
    return text.replace("</Relationships>", f"{rel}</Relationships>").encode("utf-8")


def _insert_drawing_content_type(content_xml: bytes) -> bytes:
    text = content_xml.decode("utf-8")
    if "/xl/drawings/drawing1.xml" in text:
        return content_xml
    override = (
        '<Override PartName="/xl/drawings/drawing1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
    )
    return text.replace("</Types>", f"{override}</Types>").encode("utf-8")


def _build_grid(
    layout: ToolLayout,
    metrics: _Metrics = _NORMAL,
    name_lang: str = "ja",
) -> ft.Control:
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
            controls.append(_tool_cell(left, top, tool, metrics, name_lang))
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
    name_lang: str = "ja",
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
    bg = _DISABLED_BG if not tool.enabled else _tool_color(tool.tool_name)
    name = ft.Text(
        tool_name_in(tool.tool_name, name_lang),
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
    name_lang: str = "ja",
) -> Image.Image:
    grid = _render_grid_image(layout, metrics, name_lang)
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


def _render_grid_image(
    layout: ToolLayout,
    metrics: _Metrics = _NORMAL,
    name_lang: str = "ja",
) -> Image.Image:
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
                tool_font, comment_font, metrics, mark_font, name_lang,
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
    name_lang: str = "ja",
) -> None:
    if tool is None:
        _draw_rect(draw, left, top, _CELL_W, metrics.cell_h, "#FFFFFF", "#E0E0E0")
        return
    bg = _DISABLED_BG if not tool.enabled else _tool_color(tool.tool_name)
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
    name = _fit_text(
        draw, tool_name_in(tool.tool_name, name_lang), tool_font, _px(max(8, text_width)),
    )
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
