"""
订单 JSON CRUD。

state/orders/{xianyu_order_id}.json 是唯一数据源。
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

_ORDERS_DIR = Path(__file__).parent.parent / "state" / "orders"

TZ_CST = timezone(timedelta(hours=8))

VALID_STATUSES = {
    "询价",
    "已报价",
    "已付款",
    "已发单",
    "已出票",
    "已发回执",
    "已收货",
    "已预订，待买家确认收货",
    "交易关闭",
}


def _orders_dir() -> Path:
    _ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    return _ORDERS_DIR


def _path(order_id: str) -> Path:
    return _orders_dir() / f"{order_id}.json"


def load(order_id: str) -> dict:
    p = _path(order_id)
    if not p.exists():
        raise FileNotFoundError(f"订单不存在：{order_id}")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save(order: dict) -> Path:
    order_id = order.get("xianyu_order_id")
    if not order_id:
        raise ValueError("order 缺少 xianyu_order_id")
    p = _path(order_id)
    with p.open("w", encoding="utf-8") as f:
        json.dump(order, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return p


def list_all() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(_orders_dir().glob("*.json"))
    ]


def update_status(order_id: str, status: str, note: Optional[str] = None) -> dict:
    if status not in VALID_STATUSES:
        raise ValueError(f"无效状态：{status}，可用：{sorted(VALID_STATUSES)}")
    order = load(order_id)
    order["status"] = status
    entry: dict = {
        "status": status,
        "at": datetime.now(TZ_CST).isoformat(timespec="seconds"),
    }
    if note:
        entry["note"] = note
    timeline = order.setdefault("timeline", [])
    if timeline and timeline[-1].get("status") == status:
        timeline[-1] = entry
    else:
        timeline.append(entry)
    save(order)
    return order
