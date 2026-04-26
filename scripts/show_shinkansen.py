"""
查新干线 JR 价 + Klook 客户参考价 + 报价。

用法：
  python3 scripts/show_shinkansen.py 东京 京都                  # 默认指定席
  python3 scripts/show_shinkansen.py 东京 京都 free             # 自由席
  python3 scripts/show_shinkansen.py 东京 大阪                  # 模糊匹配 → 新大阪
  python3 scripts/show_shinkansen.py 东京 大阪 --pax 2          # 2 人
  python3 scripts/show_shinkansen.py --list                     # 列所有线路
"""

import argparse
import difflib
import json
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.fx import _BUFFER, get_jpy_to_cny_mid

DATA_FILE    = _ROOT / "data" / "shinkansen_fares.json"
KLOOK_MARKUP = 1.05
QUOTE_RATIO  = 0.75
SEAT_LABEL   = {"free": "自由席", "reserved": "指定席", "green": "绿色车厢", "granclass": "Gran Class"}


def _floor50(x: float) -> int:
    return int(math.floor(x / 50) * 50)


def _all_stations(routes: list) -> set:
    s = set()
    for r in routes:
        s.add(r["from"])
        s.add(r["to"])
    return s


def _resolve_station(name: str, stations: set) -> str | None:
    """精确 → 包含 → difflib 三级模糊。返回标准站名或 None。"""
    if name in stations:
        return name
    contained = [s for s in stations if name in s or s in name]
    if len(contained) == 1:
        return contained[0]
    if len(contained) > 1:
        # 多个包含匹配，取最短的（避免"大阪"→"新大阪"反而被更长的覆盖）
        return min(contained, key=len)
    close = difflib.get_close_matches(name, list(stations), n=1, cutoff=0.5)
    return close[0] if close else None


def _find_route(routes: list, frm: str, to: str) -> dict | None:
    for r in routes:
        if r["from"] == frm and r["to"] == to:
            return r
        if r["from"] == to and r["to"] == frm:
            return r
    return None


def _list_all(routes: list) -> None:
    for r in routes:
        f = r["fare"]
        seats = " / ".join(
            f"{SEAT_LABEL[k]} {v}" for k, v in f.items() if v is not None
        ) or "暂无数据"
        print(f"{r['from']:6s} ⇄ {r['to']:10s}  ({r['line']})  {seats}")


def main() -> None:
    parser = argparse.ArgumentParser(description="查新干线票价 + 报价")
    parser.add_argument("frm",  nargs="?", help="出发站（中文）")
    parser.add_argument("to",   nargs="?", help="到达站（中文）")
    parser.add_argument("seat", nargs="?", default="reserved",
                        choices=["free", "reserved", "green", "granclass"],
                        help="席位类型，默认 reserved")
    parser.add_argument("--pax",  type=int, default=1, help="人数，默认 1")
    parser.add_argument("--list", action="store_true", help="列所有线路")
    args = parser.parse_args()

    data   = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    routes = data["routes"]

    if args.list:
        _list_all(routes)
        return

    if not args.frm or not args.to:
        parser.print_help()
        sys.exit(1)

    stations = _all_stations(routes)
    frm = _resolve_station(args.frm, stations)
    to  = _resolve_station(args.to,  stations)

    if not frm or not to:
        print(f"找不到匹配站名：from={args.frm!r} → {frm}, to={args.to!r} → {to}")
        print(f"已知站名：{', '.join(sorted(stations))}")
        sys.exit(2)

    if (frm, to) != (args.frm, args.to):
        print(f"模糊匹配：{args.frm}→{frm}, {args.to}→{to}\n")

    route = _find_route(routes, frm, to)
    if not route:
        print(f"数据里没有 {frm} ⇄ {to} 的直达线路")
        sys.exit(3)

    jr_per = route["fare"].get(args.seat)
    if jr_per is None:
        avail = [SEAT_LABEL[k] for k, v in route["fare"].items() if v is not None]
        print(f"{frm} ⇄ {to} {SEAT_LABEL[args.seat]} 暂无票价数据")
        print(f"可选席位：{', '.join(avail) or '全部缺失'}")
        sys.exit(4)

    jr_total    = jr_per * args.pax
    mid         = get_jpy_to_cny_mid()
    rate        = mid * _BUFFER
    klook_jpy   = jr_total * KLOOK_MARKUP
    klook_cny   = klook_jpy * rate
    quoted      = _floor50(klook_cny * QUOTE_RATIO)
    profit      = round(quoted - klook_cny * 0.4, 2)

    print(f"线路：{frm} ⇄ {to}  ({route['line']}, {route.get('duration_min', '?')} 分钟)")
    print(f"席位：{SEAT_LABEL[args.seat]} × {args.pax} 人")
    print()
    print(f"  JR 官方价   : {jr_per} JPY × {args.pax} = {jr_total:.0f} JPY")
    print(f"  Klook 估价  : {jr_total:.0f} × {KLOOK_MARKUP} = {klook_jpy:.0f} JPY")
    print(f"  汇率（含缓冲）: 1 JPY = {rate:.6f} CNY  (中间价 {mid:.6f} ×{_BUFFER})")
    print(f"  Klook 客户参考价: ¥{klook_cny:.0f} CNY")
    print()
    print(f"  报价 (×{QUOTE_RATIO} 抹零)  : ¥{quoted}")
    print(f"  利润预演 (回执后): ¥{profit:.0f}  = {quoted} − {klook_cny:.0f}×0.4")
    print()
    print(f"下一步（写订单 + 生成话术）：")
    print(f"  单档：python3 commands/quote.py --order-id <ID> --jpy-price {jr_per} --seat {args.seat}")
    print(f"  全档：python3 commands/quote.py --order-id <ID> --rail-route {frm}-{to}")


if __name__ == "__main__":
    main()
