"""
发单到 TG 发单群。没有 --confirm 只打印，不发送。

用法：
  python3 commands/dispatch.py --order-id ydedc_2026-04-26_hkg-tpe
  python3 commands/dispatch.py --order-id ydedc_2026-04-26_hkg-tpe --confirm
"""

import sys
import argparse
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.order_store import load, update_status
from lib.order_formatter import format_order, validate_order


def _to_dispatch_payload(order: dict) -> dict:
    """把新 schema 订单转换成 format_order() 需要的结构。"""
    item_type   = (order.get("item") or {}).get("type", "flight")
    trip        = order.get("trip") or {}
    pricing     = order.get("pricing") or {}
    travelers   = order.get("travelers") or []
    ctrip_price = str(pricing.get("ctrip_price") or "")
    price_src   = pricing.get("source") or "携程"

    if item_type == "flight":
        is_round = trip.get("is_round_trip", False)
        dep_date = trip.get("departure_date") or trip.get("date") or ""
        ret_date = trip.get("return_date") or ""
        date_str = f"{dep_date} 至 {ret_date}" if is_round and ret_date else dep_date
        item = {
            "type":             "flight",
            "origin":           trip.get("origin") or "",
            "origin_code":      trip.get("origin_code") or "",
            "destination":      trip.get("destination") or "",
            "destination_code": trip.get("destination_code") or "",
            "is_round_trip":    is_round,
            "date":             date_str,
            "ctrip_price":      ctrip_price,
            "price_source":     price_src,
            "passengers":       travelers,
        }
    elif item_type == "rail":
        item = {
            "type":                   "rail",
            "route":                  trip.get("route") or "",
            "date":                   trip.get("date") or trip.get("departure_date") or "",
            "departure_time":         trip.get("departure_time") or "",
            "is_round_trip":          trip.get("is_round_trip", False),
            "return_date":            trip.get("return_date") or "",
            "return_departure_time":  trip.get("return_departure_time") or "",
            "ticket_count":           trip.get("ticket_count") or trip.get("passenger_count") or "",
            "price_source":           price_src,
            "ctrip_price":            ctrip_price,
        }
    elif item_type == "hotel":
        item = {
            "type":        "hotel",
            "name":        trip.get("hotel_name") or (order.get("item") or {}).get("summary") or "",
            "checkin":     trip.get("checkin") or trip.get("departure_date") or "",
            "checkout":    trip.get("checkout") or trip.get("return_date") or "",
            "room_type":   trip.get("room_type") or "",
            "guests":      trip.get("passenger_count") or len(travelers),
            "breakfast":   trip.get("breakfast") or "",
            "ctrip_price": ctrip_price,
            "price_source": price_src,
            "passengers":  travelers,
        }
    else:
        raise ValueError(f"未知 item.type：{item_type}")

    return {"items": [item]}


def main() -> None:
    parser = argparse.ArgumentParser(description="发单到 TG 发单群")
    parser.add_argument("--order-id", required=True, help="订单 ID（xianyu_order_id）")
    parser.add_argument("--confirm", action="store_true", help="加此参数才真发，否则只打印")
    args = parser.parse_args()

    try:
        order = load(args.order_id)
    except FileNotFoundError:
        print(f"订单不存在：{args.order_id}")
        sys.exit(1)

    try:
        payload = _to_dispatch_payload(order)
        validate_order(payload)
        text = format_order(payload)
    except (ValueError, KeyError) as e:
        print(f"生成发单文本失败：{e}")
        sys.exit(1)

    print("发单文本预览：")
    print("─" * 40)
    print(text)
    print("─" * 40)

    if not args.confirm:
        print("\n[dry-run] 未加 --confirm，不发送")
        return

    import os
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")

    dispatch_chat_id = os.getenv("TG_DISPATCH_CHAT_ID", "")
    if not dispatch_chat_id:
        print("错误：.env 缺少 TG_DISPATCH_CHAT_ID")
        sys.exit(1)

    from lib.tg_client import send_text
    try:
        send_text(dispatch_chat_id, text)
        print(f"已发送到发单群（chat_id={dispatch_chat_id}）")
    except Exception as e:
        print(f"发送失败：{e}")
        sys.exit(1)

    update_status(args.order_id, "已发单")
    print(f"订单状态已推进：已发单")


if __name__ == "__main__":
    main()
