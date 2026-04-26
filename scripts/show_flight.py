"""
查航班参考价（Travelpayouts/Aviasales 缓存数据），对照携程报价用。

用法：
  python3 scripts/show_flight.py PEK NRT 2026-05           # 当月最低
  python3 scripts/show_flight.py PEK NRT 2026-05 --return 2026-05   # 往返
  python3 scripts/show_flight.py PEK NRT 2026-05 --calendar         # 按日列价
  python3 scripts/show_flight.py PVG HND 2026-06 --currency USD

机场码不熟用 scripts/show_airport.py 查。
数据来自 Aviasales 用户搜索缓存（非实时），仅做参考，报价仍以携程实时价为准。
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.tp_flights import search_cheap, search_calendar


def _stops_label(n: int) -> str:
    return "直飞" if n == 0 else f"{n} 次中转"


def main() -> None:
    parser = argparse.ArgumentParser(description="查航班参考价（Travelpayouts）")
    parser.add_argument("origin",      help="出发机场/城市 IATA 码（PEK / SHA / TYO）")
    parser.add_argument("destination", help="到达机场/城市 IATA 码（NRT / HND）")
    parser.add_argument("month",       help="出发月份 YYYY-MM")
    parser.add_argument("--return",    dest="return_month", help="返程月份 YYYY-MM（往返）")
    parser.add_argument("--currency",  default="CNY", help="币种，默认 CNY")
    parser.add_argument("--calendar",  action="store_true", help="按日期列出当月每天最低价")
    args = parser.parse_args()

    try:
        if args.calendar:
            results = search_calendar(
                origin=args.origin,
                destination=args.destination,
                depart_month=args.month,
                currency=args.currency,
            )
            if not results:
                print("无数据（缓存里没有该航线该月记录）")
                sys.exit(3)
            print(f"日历价：{args.origin} → {args.destination}  {args.month}  ({args.currency})\n")
            for r in results:
                print(f"  {r['date']}  {r['currency']} {r['price']:>6}  "
                      f"{_stops_label(r['stops']):5s}  {r['airline']}{r['flight_number']}")
        else:
            results = search_cheap(
                origin=args.origin,
                destination=args.destination,
                depart_month=args.month,
                return_month=args.return_month,
                currency=args.currency,
            )
            if not results:
                print("无数据（缓存里没有该航线该月记录）")
                sys.exit(3)
            trip = f"{args.origin} → {args.destination}"
            if args.return_month:
                trip += f" → {args.origin}"
            print(f"航线：{trip}  {args.month}"
                  + (f" / 返程 {args.return_month}" if args.return_month else "")
                  + f"  ({len(results)} 条, Aviasales 缓存)\n")
            for i, r in enumerate(results, 1):
                print(f"  [{i}] {r['currency']} {r['price']:>6}  {_stops_label(r['stops']):5s}"
                      f"  出发 {r['departure_at'][:16]}  {r['airline']}{r['flight_number']}")

    except RuntimeError as e:
        print(f"查询失败：{e}", file=sys.stderr)
        sys.exit(2)

    print("\n（数据来自 Aviasales 缓存，非实时，报价仍以携程实时价 ×0.75 抹零为准）")


if __name__ == "__main__":
    main()
