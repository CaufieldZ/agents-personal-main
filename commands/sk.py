#!/usr/bin/env python3
"""查询新干线票价。用法：sk.py --from 东京 --to 京都 [--type reserved] [--adults 2] [--children 1]"""

import argparse
import json
import math
import sys
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "shinkansen_fares.json"

SEAT_TYPES = {
    "free": "自由席",
    "reserved": "指定席",
    "green": "绿色车厢",
    "granclass": "GranClass",
}


def load_fares():
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def normalize(s: str) -> str:
    return s.strip().lower().replace(" ", "").replace("　", "")


def find_route(routes, frm, to):
    nfrm, nto = normalize(frm), normalize(to)
    for r in routes:
        a = normalize(r["from"])
        b = normalize(r["to"])
        a_jr = normalize(r["from_jr"])
        b_jr = normalize(r["to_jr"])
        if (a == nfrm or a_jr == nfrm) and (b == nto or b_jr == nto):
            return r, False
        if (a == nto or a_jr == nto) and (b == nfrm or b_jr == nfrm):
            return r, True
    return None, None


def child_fare(adult_fare: int) -> int:
    return math.ceil(adult_fare / 2 / 10) * 10  # 四舍五入到10円


def main():
    parser = argparse.ArgumentParser(description="新干线票价查询")
    parser.add_argument("--from", dest="frm", required=True, metavar="STATION", help="出发站（中文或英文）")
    parser.add_argument("--to", required=True, metavar="STATION", help="到达站（中文或英文）")
    parser.add_argument("--type", dest="seat_type", default="reserved",
                        choices=list(SEAT_TYPES.keys()), help="席别（默认 reserved）")
    parser.add_argument("--adults", type=int, default=1, help="成人人数（默认 1）")
    parser.add_argument("--children", type=int, default=0, help="儿童人数（默认 0）")
    parser.add_argument("--all-types", action="store_true", help="列出所有席别价格")
    args = parser.parse_args()

    data = load_fares()
    route, reversed_dir = find_route(data["routes"], args.frm, args.to)

    if route is None:
        print(f"未找到路线：{args.frm} → {args.to}", file=sys.stderr)
        print("可用站点：", file=sys.stderr)
        stations = sorted({r["from"] for r in data["routes"]} | {r["to"] for r in data["routes"]})
        print("  " + "、".join(stations), file=sys.stderr)
        sys.exit(1)

    frm_label = route["to"] if reversed_dir else route["from"]
    to_label = route["from"] if reversed_dir else route["to"]

    print(f"{'─'*40}")
    print(f"  {frm_label} → {to_label}（{route['line']}）")
    print(f"  所需时间：约 {route['duration_min']} 分钟")
    print(f"  数据更新：{data['updated_at']}")
    print(f"{'─'*40}")

    if args.all_types:
        for stype, label in SEAT_TYPES.items():
            price = route["fare"].get(stype)
            if price is None:
                print(f"  {label:<10}  不设")
                continue
            adult_total = price * args.adults
            child_total = child_fare(price) * args.children
            total = adult_total + child_total
            parts = [f"成人×{args.adults} ¥{adult_total:,}"]
            if args.children:
                parts.append(f"儿童×{args.children} ¥{child_total:,}")
            print(f"  {label:<10}  ¥{total:,}  ({' + '.join(parts)})")
    else:
        stype = args.seat_type
        price = route["fare"].get(stype)
        if price is None:
            print(f"  该路线不设{SEAT_TYPES[stype]}，请换席别。")
            sys.exit(1)

        adult_total = price * args.adults
        child_total = child_fare(price) * args.children
        total = adult_total + child_total

        print(f"  席别：{SEAT_TYPES[stype]}")
        print(f"  单价：¥{price:,}（成人）/ ¥{child_fare(price):,}（儿童）")
        if args.adults or args.children:
            parts = []
            if args.adults:
                parts.append(f"成人×{args.adults} ¥{adult_total:,}")
            if args.children:
                parts.append(f"儿童×{args.children} ¥{child_total:,}")
            print(f"  合计：¥{total:,}  ({' + '.join(parts)})")

    print(f"{'─'*40}")


if __name__ == "__main__":
    main()
