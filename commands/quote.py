"""
生成报价话术 + 写入订单 JSON。可选 --send 直发买家。

用法（首报）：
  python3 commands/quote.py --order-id X --ctrip-price 2012             # 飞机/酒店
  python3 commands/quote.py --order-id X --jpy-price 8340               # 铁路单档（按 --seat，默认指定席）
  python3 commands/quote.py --order-id X --rail-route 东京-长野          # 铁路全档（自由/指定/绿色/Gran）

改价：
  python3 commands/quote.py --order-id X --price 280                    # 沿用订单已有原价，直接改报价
  python3 commands/quote.py --order-id X --price 280 --send             # 改价并立刻发买家

一键报价 + 发：
  python3 commands/quote.py --order-id X --jpy-price 8340 --send

参数：
  --ratio 0.75      折扣，默认 0.75
  --markup 1.05     Klook 在 JR 价上的上浮（仅 --jpy-price / --rail-route）
  --pax N           人数，缺省读订单 trip.passenger_count
"""

import argparse
import json
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "vendor" / "xianyu_live"))

from lib.fx import _BUFFER, get_jpy_to_cny_mid
from lib.order_store import load, save, update_status

KLOOK_MARKUP = 1.05
SEAT_LABEL   = {"free": "自由席", "reserved": "指定席", "green": "绿色车厢", "granclass": "Gran Class"}


def _floor10(price: float) -> int:
    return int(math.floor(price / 10) * 10)


def _floor50(price: float) -> int:
    return int(math.floor(price / 50) * 50)


def _fmt_date(date_str: str) -> str:
    try:
        from datetime import datetime
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.month}/{d.day}"
    except Exception:
        return date_str


def _trip_head(order: dict) -> tuple[str, str]:
    """返回 (路线, 日期段) 用于话术开头。"""
    trip  = order.get("trip") or {}
    route = trip.get("route", "")
    if not route:
        o, d = trip.get("origin", ""), trip.get("destination", "")
        if o and d:
            sep   = "↔" if trip.get("is_round_trip") else "→"
            route = f"{o}{sep}{d}"
    dep_str = _fmt_date(trip.get("departure_date", ""))
    ret_str = _fmt_date(trip.get("return_date", "")) if trip.get("is_round_trip") else ""
    date_part = f"{dep_str}~{ret_str}" if dep_str and ret_str else dep_str
    return route, date_part


def _quote_text_single(order: dict, quoted_price: int) -> str:
    item  = order.get("item") or {}
    trip  = order.get("trip") or {}
    itype = item.get("type", "")
    route, date_part = _trip_head(order)
    pax = int(trip.get("passenger_count") or trip.get("ticket_count") or 1)
    pax_part = f"，{pax}人" if pax > 1 else ""
    head = f"{route} {date_part}".strip() if (route or date_part) else ""
    tail = {"rail": "确认就拍，我这边下单", "flight": "确认就拍，我这边出票", "hotel": "确认就拍，我这边下单"}.get(itype, "确认就拍")
    if head:
        return f"查了一下，{head}{pax_part}，¥{quoted_price}，{tail}。"
    summary = item.get("summary", "")
    if summary:
        return f"查了一下{summary}，¥{quoted_price}，{tail}。"
    return f"¥{quoted_price}，{tail}。"


def _quote_text_rail_multi(order: dict, options: dict) -> str:
    trip = order.get("trip") or {}
    route, date_part = _trip_head(order)
    pax = int(trip.get("passenger_count") or trip.get("ticket_count") or 1)
    pax_part = f"，{pax}人" if pax > 1 else ""
    head = f"{route} {date_part}".strip()
    seat_part = " / ".join(f"{SEAT_LABEL[k]} ¥{v}" for k, v in options.items())
    return f"查了一下，{head}{pax_part}，{seat_part}，确认哪档我这边下单。"


def _resolve_rail_route(arg: str) -> tuple[str, str, dict]:
    if "-" not in arg:
        print(f"--rail-route 格式应为 '东京-长野'，收到 {arg!r}")
        sys.exit(2)
    frm, to = arg.split("-", 1)
    data = json.loads((_ROOT / "data" / "shinkansen_fares.json").read_text(encoding="utf-8"))
    for r in data["routes"]:
        if (r["from"], r["to"]) == (frm, to) or (r["from"], r["to"]) == (to, frm):
            return frm, to, r
    print(f"shinkansen_fares.json 没有 {frm} ⇄ {to}，先 `python3 scripts/show_shinkansen.py --list`")
    sys.exit(3)


def _send_via_reply(order: dict, text: str, force_night: bool = False) -> None:
    chat_id = order.get("xianyu_chat_id", "")
    buyer   = order.get("buyer") or {}
    to_uid  = buyer.get("xianyu_uid", "") if isinstance(buyer, dict) else ""
    if not chat_id or not to_uid:
        print("订单缺 xianyu_chat_id 或 buyer.xianyu_uid，--send 不能用，自己 reply.py 发")
        sys.exit(5)
    from lib.xianyu_client import send_message
    send_message(chat_id, to_uid, text, force_night=force_night)
    print(f"已发买家：{chat_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成报价 + 可选直发", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--ctrip-price", type=float, help="飞机/酒店 CNY 原价")
    parser.add_argument("--jpy-price",   type=float, help="铁路单档 JPY")
    parser.add_argument("--rail-route",  help="铁路全档，例：东京-长野")
    parser.add_argument("--seat",        default="reserved",
                        choices=["free", "reserved", "green", "granclass"],
                        help="--jpy-price 时的席位类型，默认 reserved")
    parser.add_argument("--ratio",  type=float, default=0.75)
    parser.add_argument("--markup", type=float, default=KLOOK_MARKUP)
    parser.add_argument("--price",  type=float, help="直接指定报价（覆盖 ratio）")
    parser.add_argument("--pax",    type=int, help="人数，缺省读订单")
    parser.add_argument("--quoted-text", help="覆盖模板生成的话术（截图场景手写话术用）")
    parser.add_argument("--send",   action="store_true", help="生成后立刻发买家")
    parser.add_argument("--force-night", action="store_true", help="夜间静默期 (01:00-07:30 CST) 强制发送")
    args = parser.parse_args()

    try:
        order = load(args.order_id)
    except FileNotFoundError:
        print(f"订单不存在：{args.order_id}")
        sys.exit(1)

    pricing = order.setdefault("pricing", {})
    trip    = order.get("trip") or {}
    pax     = args.pax or int(trip.get("passenger_count") or trip.get("ticket_count") or 1)

    # ── 模式 1：铁路全档 ──────────────────────────────
    if args.rail_route:
        frm, to, route = _resolve_rail_route(args.rail_route)
        mid  = get_jpy_to_cny_mid()
        rate = mid * _BUFFER
        options: dict = {}
        for seat, jpy_per in route["fare"].items():
            if jpy_per is None:
                continue
            klook_cny = jpy_per * pax * args.markup * rate
            options[seat] = _floor10(klook_cny * args.ratio)
        if not options:
            print(f"{frm} ⇄ {to} 全部席位都没价"); sys.exit(4)
        pricing["rail_route"]      = f"{frm}-{to}"
        pricing["quoted_options"]  = options
        pricing["quoted_price"]    = min(options.values())
        pricing["source"]          = "Klook"
        pricing["currency"]        = "CNY"
        text = _quote_text_rail_multi(order, options)
        note = f"铁路全档 {frm}-{to}: " + " / ".join(f"{SEAT_LABEL[k]}¥{v}" for k, v in options.items())

    # ── 模式 2：--price 改价（沿用原价） ──────────────
    elif args.price and not (args.ctrip_price or args.jpy_price):
        if "ctrip_price" not in pricing:
            print("--price 单独使用时，订单需先有 pricing.ctrip_price（先跑一次 --ctrip-price 或 --jpy-price）")
            sys.exit(2)
        pricing["quoted_price"] = _floor10(args.price) if args.price >= 100 else int(args.price)
        # 单档话术
        text = _quote_text_single(order, pricing["quoted_price"])
        note = f"改价至 {pricing['quoted_price']} 元"

    # ── 模式 3：单档铁路（JR JPY） ────────────────────
    elif args.jpy_price:
        mid       = get_jpy_to_cny_mid()
        rate      = mid * _BUFFER
        klook_jpy = args.jpy_price * pax * args.markup
        cost_cny  = round(klook_jpy * rate, 2)
        raw       = args.price if args.price else cost_cny * args.ratio
        quoted    = _floor10(raw)
        pricing["ctrip_price"]   = cost_cny
        pricing["jpy_jr_price"]  = args.jpy_price
        pricing["markup"]        = args.markup
        pricing["seat"]          = args.seat
        pricing["quoted_price"]  = quoted
        pricing["source"]        = "Klook"
        pricing["currency"]      = "CNY"
        text = _quote_text_single(order, quoted)
        note = f"报价 {quoted} 元（JR {args.jpy_price:.0f}JPY × {args.markup} × {rate:.4f} = ¥{cost_cny:.0f}）"

    # ── 模式 4：飞机/酒店（携程 CNY） ────────────────
    elif args.ctrip_price:
        cost_cny = args.ctrip_price
        raw      = args.price if args.price else cost_cny * args.ratio
        quoted   = _floor10(raw)
        pricing["ctrip_price"]  = cost_cny
        pricing["quoted_price"] = quoted
        pricing["source"]       = "携程"
        pricing["currency"]     = "CNY"
        text = _quote_text_single(order, quoted)
        note = f"报价 {quoted} 元（携程 {cost_cny:.0f} × {args.ratio:.0%}）"

    else:
        print("需要 --ctrip-price / --jpy-price / --rail-route 之一，或 --price 改价")
        sys.exit(2)

    if args.quoted_text:
        text = args.quoted_text.strip()
        note = f"{note}（手写话术覆盖）"
    pricing["quoted_text"] = text
    save(order)
    update_status(args.order_id, "已报价", note)

    print("话术：")
    print("─" * 40)
    print(text)
    print("─" * 40)
    print(f"已写入 pricing.quoted_text  报价 ¥{pricing['quoted_price']}")

    if args.send:
        _send_via_reply(order, text, force_night=args.force_night)
    else:
        print(f"发买家：python3 commands/reply.py --order-id {args.order_id} --use-quoted-text --confirm")


if __name__ == "__main__":
    main()
