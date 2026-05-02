"""
生成报价话术草稿，写入订单 JSON，不发送。

用法：
  python3 commands/quote.py --order-id <id> --ctrip-price 2012
  python3 commands/quote.py --order-id <id> --ctrip-price 2012 --ratio 0.8
  python3 commands/quote.py --order-id <id> --ctrip-price 2012 --price 1500
  python3 commands/quote.py --order-id <id> --jpy-price 14170           # 新干线 JR 官方 JPY 价
  python3 commands/quote.py --order-id <id> --jpy-price 14170 --markup 1.07
"""

import argparse
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.fx import _BUFFER, get_jpy_to_cny_mid
from lib.order_store import load, save, update_status

KLOOK_MARKUP = 1.05


def _floor10(price: float) -> int:
    """抹零到 10 的倍数（向下取整）。"""
    return int(math.floor(price / 10) * 10)


def _fmt_date(date_str: str) -> str:
    try:
        from datetime import datetime
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.month}/{d.day}"
    except Exception:
        return date_str


def _quote_text(order: dict, quoted_price: int) -> str:
    item  = order.get("item") or {}
    trip  = order.get("trip") or {}
    itype = item.get("type", "")

    # 路线：优先用已格式化的 trip.route，否则自己拼
    route = trip.get("route", "")
    if not route:
        o, d = trip.get("origin", ""), trip.get("destination", "")
        if o and d:
            sep   = "↔" if trip.get("is_round_trip") else "→"
            route = f"{o}{sep}{d}"

    # 日期
    dep_str = _fmt_date(trip.get("departure_date", ""))
    ret_str = _fmt_date(trip.get("return_date", "")) if trip.get("is_round_trip") else ""
    if dep_str and ret_str:
        date_part = f"{dep_str}~{ret_str}"
    else:
        date_part = dep_str

    # 人数（1人不写）
    pax = int(trip.get("passenger_count") or trip.get("ticket_count") or 1)
    pax_part = f"，{pax}人" if pax > 1 else ""

    # 行程前缀
    head = f"{route} {date_part}".strip() if (route or date_part) else ""

    # 结尾动词
    if itype == "rail":
        action = "付了下单"
    elif itype == "flight":
        action = "付了出票"
    elif itype == "hotel":
        action = "确认拍"
    else:
        action = "付了操作"

    if head:
        return f"{head}{pax_part}，¥{quoted_price}，{action}。"

    # 兜底：用 summary
    summary = item.get("summary", "")
    if summary:
        return f"{summary}，¥{quoted_price}，{action}。"
    return f"¥{quoted_price}，{action}。"


def main() -> None:
    parser = argparse.ArgumentParser(description="生成报价草稿")
    parser.add_argument("--order-id", required=True, help="订单 ID（xianyu_order_id）")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--ctrip-price", type=float, help="携程 CNY 原价")
    src.add_argument("--jpy-price",   type=float, help="新干线 JR 官方 JPY 价（自动 × markup × 汇率 → Klook CNY）")
    parser.add_argument("--markup",   type=float, default=KLOOK_MARKUP,
                        help=f"Klook 在 JR 价上的上浮（默认 {KLOOK_MARKUP}）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--ratio", type=float, default=0.75, help="折扣比例，默认 0.75")
    group.add_argument("--price", type=float, help="直接指定报价（覆盖 ratio）")
    args = parser.parse_args()

    try:
        order = load(args.order_id)
    except FileNotFoundError:
        print(f"订单不存在：{args.order_id}")
        sys.exit(1)

    if args.jpy_price:
        mid       = get_jpy_to_cny_mid()
        rate      = mid * _BUFFER
        klook_jpy = args.jpy_price * args.markup
        cost_cny  = round(klook_jpy * rate, 2)
        source    = "Klook"
        cost_note = (
            f"JR {args.jpy_price:.0f} JPY × markup {args.markup} × {rate:.6f}（中间价 {mid:.6f} ×{_BUFFER}）"
            f"= Klook 客户参考价 ¥{cost_cny:.0f}"
        )
        print(f"JR {args.jpy_price:.0f} JPY × {args.markup} markup = {klook_jpy:.0f} JPY")
        print(f"汇率：1 JPY = {rate:.6f} CNY  →  Klook 客户参考价 ¥{cost_cny:.0f}")
    else:
        cost_cny  = args.ctrip_price
        source    = "携程"
        cost_note = f"携程 {cost_cny:.0f} × {args.ratio:.0%}"

    raw_price = args.price if args.price else cost_cny * args.ratio
    quoted    = _floor10(raw_price)

    order.setdefault("pricing", {})
    order["pricing"]["ctrip_price"]  = cost_cny
    order["pricing"]["quoted_price"] = quoted
    order["pricing"]["source"]       = source
    if args.jpy_price:
        order["pricing"]["jpy_jr_price"] = args.jpy_price
        order["pricing"]["markup"]       = args.markup
    save(order)

    update_status(args.order_id, "已报价", f"报价 {quoted} 元（{cost_note}）")

    text = _quote_text(order, quoted)
    print("报价话术草稿（未发送）：")
    print("─" * 40)
    print(text)
    print("─" * 40)
    print(f"原价：¥{cost_cny:.0f}（{source}）  报价：¥{quoted}  已写入订单 JSON")
    print(f"发送：python3 commands/reply.py --order-id {args.order_id} --text '...' --confirm")


if __name__ == "__main__":
    main()
