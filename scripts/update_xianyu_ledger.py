"""
从 state/orders/*.json 生成闲鱼台账 Excel。

用法：
  python3 scripts/update_xianyu_ledger.py
  python3 scripts/update_xianyu_ledger.py --orders-dir state/orders --out xianyu/ledger.xlsx
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.order_store import list_all
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

DEFAULT_OUT = Path("xianyu/ledger.xlsx")

# 列定义：(header, min_width, max_width, align)
COLUMNS = [
    ("日期",       11, 11, "center"),
    ("订单号",     18, 24, "left"),
    ("商品",       22, 36, "left"),
    ("买家",       12, 18, "left"),
    ("成交价",      9,  9, "right"),
    ("携程价",      9,  9, "right"),
    ("利润",        8,  8, "right"),
    ("状态",        9,  9, "center"),
    ("关联PNR",    14, 20, "left"),
    ("备注",       16, 32, "left"),
]

STATUS_COLORS = {
    "已收货":   ("D6F4E4", "1A7A45"),
    "已发回执": ("D6F4E4", "1A7A45"),
    "已出票":   ("D6F4E4", "1A7A45"),
    "已付款":   ("FFF3CC", "8A6000"),
    "已发单":   ("FFF3CC", "8A6000"),
    "交易关闭": ("FCE4E4", "9B1C1C"),
}

C_HEADER_BG  = "1C3557"
C_HEADER_FG  = "FFFFFF"
C_ALT_ROW    = "F4F7FB"
C_TOTAL_BG   = "E8EEF6"
C_PROFIT_POS = "1A7A45"
C_PROFIT_NEG = "C0392B"
C_BORDER     = "D0D8E4"

MONEY_FMT = '¥#,##0'
DATE_FMT  = 'yyyy-mm-dd'

# 实际下单成本 = 携程价 × COST_RATIO
COST_RATIO = 0.4

# 利润仅在订单已交付（PNR/取票码/入住码已发回执，或买家已收货）后才计入
PROFIT_STATUSES = {"已发回执", "已收货"}
HEADER_ROW_H = 22
DATA_ROW_H   = 18
TOTAL_ROW_H  = 20


def _side(color=C_BORDER):
    return Side(border_style="thin", color=color)


def _border(color=C_BORDER):
    s = _side(color)
    return Border(left=s, right=s, top=s, bottom=s)


def _fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)


def _font(bold=False, color="000000", size=10):
    return Font(name="PingFang SC", bold=bold, color=color, size=size)


def _order_date(order: dict) -> str:
    tl = order.get("timeline", [])
    if tl:
        return tl[0].get("at", "")[:10]
    return ""


def order_to_row(o: dict) -> list:
    pricing  = o.get("pricing", {})
    buyer    = o.get("buyer", {})
    item     = o.get("item", {})
    ff       = o.get("fulfillment", {})
    notes    = o.get("notes", [])

    sale     = pricing.get("quoted_price") or 0
    ctrip    = pricing.get("ctrip_price") or 0
    status   = o.get("status", "")
    if status in PROFIT_STATUSES and sale and ctrip:
        profit = round(sale - ctrip * COST_RATIO, 2)
    else:
        profit = ""

    note_str = "；".join(notes) if isinstance(notes, list) else str(notes or "")

    return [
        _order_date(o),
        o.get("xianyu_order_id", ""),
        item.get("summary", "") if isinstance(item, dict) else str(item),
        buyer.get("nick", "") if isinstance(buyer, dict) else str(buyer),
        sale or "",
        ctrip or "",
        profit,
        o.get("status", ""),
        ff.get("supplier_pnr", "") if isinstance(ff, dict) else "",
        note_str,
    ]


def write_ledger(rows: list[list], out_path: Path) -> float:
    wb = Workbook()
    ws = wb.active
    ws.title = "闲鱼台账"
    ws.sheet_view.showGridLines = False

    n_cols = len(COLUMNS)

    ws.row_dimensions[1].height = HEADER_ROW_H
    for col_idx, (header, *_) in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill      = _fill(C_HEADER_BG)
        cell.font      = _font(bold=True, color=C_HEADER_FG, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border    = _border()

    for r_idx, row in enumerate(rows, 2):
        ws.row_dimensions[r_idx].height = DATA_ROW_H
        is_alt = (r_idx % 2 == 0)
        status = row[7] if len(row) > 7 else ""

        for c_idx, value in enumerate(row, 1):
            _, min_w, max_w, align = COLUMNS[c_idx - 1]
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.border    = _border()
            cell.alignment = Alignment(
                horizontal=align, vertical="center", wrap_text=(c_idx == 10)
            )

            if c_idx in (5, 6):
                cell.number_format = MONEY_FMT
                cell.font = _font(size=10)
            elif c_idx == 7:
                profit_val = value if isinstance(value, (int, float)) else 0
                color = C_PROFIT_POS if profit_val >= 0 else C_PROFIT_NEG
                cell.number_format = MONEY_FMT
                cell.font = _font(bold=True, color=color, size=10)
            elif c_idx == 1:
                cell.number_format = DATE_FMT
                cell.font = _font(size=10)
            elif c_idx == 8:
                bg, fg = STATUS_COLORS.get(status, ("EEEEEE", "555555"))
                cell.fill = _fill(bg)
                cell.font = _font(bold=True, color=fg, size=9)
            else:
                cell.font = _font(size=10)

            if is_alt and c_idx not in (7, 8):
                if cell.fill.fgColor.rgb in ("00000000", "FFFFFFFF", "00FFFFFF"):
                    cell.fill = _fill(C_ALT_ROW)

    total_row = len(rows) + 2
    ws.row_dimensions[total_row].height = TOTAL_ROW_H

    total_sale   = sum(r[4] for r in rows if isinstance(r[4], (int, float)))
    total_cost   = sum(r[5] for r in rows if isinstance(r[5], (int, float)))
    total_profit = sum(r[6] for r in rows if isinstance(r[6], (int, float)))

    totals = {1: f"共 {len(rows)} 笔", 5: total_sale, 6: total_cost, 7: total_profit}

    for c_idx in range(1, n_cols + 1):
        value = totals.get(c_idx, "")
        cell = ws.cell(row=total_row, column=c_idx, value=value)
        cell.fill      = _fill(C_TOTAL_BG)
        cell.border    = _border(C_HEADER_BG)
        cell.alignment = Alignment(
            horizontal="right" if c_idx in (5, 6, 7) else "left",
            vertical="center",
        )
        if c_idx in (5, 6):
            cell.number_format = MONEY_FMT
            cell.font = _font(bold=True, size=10)
        elif c_idx == 7:
            color = C_PROFIT_POS if total_profit >= 0 else C_PROFIT_NEG
            cell.number_format = MONEY_FMT
            cell.font = _font(bold=True, color=color, size=10)
        else:
            cell.font = _font(bold=True, size=10)

    for col_idx, (_, min_w, max_w, _) in enumerate(COLUMNS, 1):
        letter = get_column_letter(col_idx)
        best = min_w
        for r in range(1, total_row + 1):
            v = ws.cell(row=r, column=col_idx).value
            if v:
                best = max(best, min(len(str(v)) * 1.5, max_w))
        ws.column_dimensions[letter].width = max(min_w, min(best, max_w))

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{len(rows) + 1}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return total_profit


def build_ledger(out_path: Path) -> None:
    orders = list_all()
    rows = [order_to_row(o) for o in orders]
    total_profit = write_ledger(rows, out_path)
    print(f"台账文件：{out_path}")
    print(f"订单数量：{len(rows)}  累计利润：¥{total_profit:.0f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="刷新闲鱼 Excel 台账")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_ledger(args.out)
