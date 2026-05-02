"""
一次性迁移脚本：把 travel/orders/*.json 转成新 schema 写入 state/orders/。

用法：
  python3 scripts/migrate_codex_orders.py [--dry-run]

旧文件原地保留（不删除），迁移后可手动清理。
"""

import argparse
import json
import sys
from datetime import timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.order_store import save

TZ_CST = timezone(timedelta(hours=8))

TRAVEL_ORDERS_DIR = _ROOT / "travel" / "orders"
STATE_ORDERS_DIR  = _ROOT / "state" / "orders"

# 旧 trip.type → item.type
ITEM_TYPE_MAP = {
    "往返机票": "flight",
    "单程机票": "flight",
    "机票":     "flight",
    "新干线":   "rail",
    "铁路":     "rail",
    "火车":     "rail",
    "酒店":     "hotel",
}


def _item_type(trip_type: str) -> str:
    for k, v in ITEM_TYPE_MAP.items():
        if k in trip_type:
            return v
    return "flight"


def _map_gender(raw: str) -> str:
    if not raw:
        return ""
    u = raw.upper()
    if u in ("MALE", "M", "男"):
        return "男"
    if u in ("FEMALE", "F", "女"):
        return "女"
    return raw


def _build_travelers(order: dict) -> list:
    traveler = order.get("traveler")
    if not traveler:
        return []
    return [{
        "name_cn":         traveler.get("name_cn", ""),
        "name_en":         traveler.get("name_en") or " ".join(
            p for p in [traveler.get("surname_en", ""), traveler.get("given_name_en", "")] if p
        ),
        "gender":          _map_gender(traveler.get("gender", "")),
        "passport":        traveler.get("passport_number", ""),
        "passport_expiry": traveler.get("passport_expiry", ""),
        "dob":             traveler.get("birth_date", ""),
        "nationality":     traveler.get("nationality", ""),
        "baggage":         "",
    }]


def _build_timeline(order: dict) -> list:
    created = order.get("created_at", "")
    status  = order.get("status", "询价")
    # 用文件里的 created_at 作为第一条时间戳
    at = created if created else "2026-01-01T00:00:00+08:00"
    return [{"status": status, "at": at}]


def _infer_order_id(path: Path) -> str:
    # 用文件名（去掉 _send 后缀）作为 ID
    stem = path.stem
    if stem.endswith("_send"):
        stem = stem[:-5]
    return stem


def convert(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        old = json.load(f)

    trip    = old.get("trip", {})
    pricing = old.get("pricing", {})
    item_type = _item_type(trip.get("type", ""))

    order_id = _infer_order_id(path)

    new: dict = {
        "xianyu_order_id": order_id,
        "xianyu_chat_id":  "",
        "buyer": {
            "nick":        old.get("buyer", ""),
            "xianyu_uid":  "",
        },
        "item": {
            "type":          item_type,
            "summary":       old.get("item", ""),
            "xianyu_item_id": "",
        },
        "trip": {
            "origin":            trip.get("origin", ""),
            "origin_code":       trip.get("origin_code", ""),
            "destination":       trip.get("destination", ""),
            "destination_code":  trip.get("destination_code", ""),
            "is_round_trip":     bool(trip.get("return_date")) or "往返" in trip.get("type", ""),
            "departure_date":    trip.get("departure_date") or trip.get("date", ""),
            "return_date":       trip.get("return_date", ""),
            "departure_time":    trip.get("departure_time", ""),
            "passenger_count":   trip.get("passenger_count", 1),
            "ticket_count":      trip.get("ticket_count") or trip.get("passenger_count", 1),
            "route":             trip.get("route", ""),
            "airline":           trip.get("airline", ""),
        },
        "travelers": _build_travelers(old),
        "pricing": {
            "ctrip_price":  pricing.get("ctrip_price"),
            "quoted_price": old.get("deal_price"),
            "currency":     pricing.get("currency", "CNY"),
            "source":       pricing.get("source", "携程"),
        },
        "status":   old.get("status", ""),
        "timeline": _build_timeline(old),
        "fulfillment": {
            "supplier_pnr":          trip.get("booking_reference", ""),
            "supplier_attachments":  [],
            "buyer_receipt_sent_at": None,
        },
        "notes": old.get("notes", []) if isinstance(old.get("notes"), list) else (
            [old["notes"]] if old.get("notes") else []
        ),
    }
    return new


def should_skip(path: Path) -> bool:
    name = path.name
    return name.endswith("_send.json") or name.startswith("sample_")


def main(dry_run: bool) -> None:
    candidates = [p for p in sorted(TRAVEL_ORDERS_DIR.glob("*.json")) if not should_skip(p)]

    if not candidates:
        print("travel/orders/ 里没有可迁移的文件")
        return

    print(f"找到 {len(candidates)} 笔订单待迁移：")
    for p in candidates:
        print(f"  {p.name}")

    if dry_run:
        print("\n[dry-run] 不写入文件，退出")
        return

    STATE_ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    migrated = 0
    for p in candidates:
        try:
            new_order = convert(p)
            out = save(new_order)
            print(f"  {p.name}  →  {out.name}")
            migrated += 1
        except Exception as e:
            print(f"  {p.name}  失败：{e}", file=sys.stderr)

    print(f"\n迁移完成：{migrated}/{len(candidates)} 笔")
    print("旧文件保留在 travel/orders/，确认无误后可手动删除")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="迁移旧订单到 state/orders/")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = parser.parse_args()
    main(args.dry_run)
