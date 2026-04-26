"""
查机场三字码 / 城市机场列表。

用法：
  python3 scripts/show_airport.py HND               # 单机场详情
  python3 scripts/show_airport.py 东京              # 城市所有机场
  python3 scripts/show_airport.py tokyo             # 英文城市
  python3 scripts/show_airport.py TYO               # 城市码
  python3 scripts/show_airport.py --multi           # 仅列多机场城市
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).parent.parent
DATA  = _ROOT / "data" / "airport_codes.json"


def _row(a: dict) -> str:
    return f"  {a['iata']}  {a['name_cn']:8s} {a['name_en']:22s}  {a['note']}"


def main() -> None:
    parser = argparse.ArgumentParser(description="查机场 IATA 三字码")
    parser.add_argument("query", nargs="?", help="三字码 / 城市中英文 / 城市码")
    parser.add_argument("--multi", action="store_true", help="只列多机场城市")
    args = parser.parse_args()

    airports = json.loads(DATA.read_text(encoding="utf-8"))["airports"]

    if args.multi:
        by_city: dict[str, list] = defaultdict(list)
        for a in airports:
            by_city[a["city_iata"]].append(a)
        for city, group in sorted(by_city.items()):
            if len(group) < 2:
                continue
            head = group[0]
            print(f"\n{head['city_cn']} / {head['city_en']} ({city}) — {len(group)} 个机场")
            for a in group:
                print(_row(a))
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    q = args.query.strip().lower()

    # 先按 IATA 三字码精确匹配
    exact = [a for a in airports if a["iata"].lower() == q]
    if len(exact) == 1:
        a = exact[0]
        print(f"{a['name_cn']} {a['name_en']}  ({a['iata']})")
        print(f"  城市：{a['city_cn']} / {a['city_en']}  ({a['city_iata']}, {a['country']})")
        print(f"  备注：{a['note']}")
        same_city = [x for x in airports if x["city_iata"] == a["city_iata"] and x["iata"] != a["iata"]]
        if same_city:
            print(f"\n同城其他机场：")
            for x in same_city:
                print(_row(x))
        return

    # 城市码 / 城市名匹配
    matched = [
        a for a in airports
        if q == a["city_iata"].lower()
        or q in a["city_cn"].lower()
        or q in a["city_en"].lower()
    ]
    if not matched:
        print(f"找不到匹配：{args.query!r}")
        sys.exit(2)

    by_city = defaultdict(list)
    for a in matched:
        by_city[a["city_iata"]].append(a)
    for city, group in by_city.items():
        head = group[0]
        n_same_city = len([x for x in airports if x["city_iata"] == city])
        marker = f" — {n_same_city} 个机场" if n_same_city > 1 else ""
        print(f"\n{head['city_cn']} / {head['city_en']} ({city}, {head['country']}){marker}")
        for a in [x for x in airports if x["city_iata"] == city]:
            print(_row(a))


if __name__ == "__main__":
    main()
