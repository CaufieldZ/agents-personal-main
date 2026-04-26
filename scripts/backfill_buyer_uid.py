"""
从 state/incoming/chat_*.json 反查买家 xianyu_uid，回填到订单 JSON。

用法：
  python3 scripts/backfill_buyer_uid.py                     # 列出所有缺 uid 的订单 + 候选 uid
  python3 scripts/backfill_buyer_uid.py --apply             # 真写入
  python3 scripts/backfill_buyer_uid.py --order-id X --apply
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.order_store import load, save, list_all

_INCOMING = _ROOT / "state" / "incoming"


def _build_chat_to_uid() -> dict[str, str]:
    """{chat_id: sender_id of incoming side}"""
    out: dict[str, str] = {}
    for p in sorted(_INCOMING.glob("chat_*.json")):
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if ev.get("direction") == "out":
            continue
        chat_id = ev.get("chat_id", "")
        uid     = ev.get("sender_id", "")
        if chat_id and uid:
            out.setdefault(chat_id, uid)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="回填订单的 buyer.xianyu_uid")
    parser.add_argument("--order-id", help="只处理指定订单")
    parser.add_argument("--apply",    action="store_true", help="真写入，不加只 dry-run")
    args = parser.parse_args()

    chat_to_uid = _build_chat_to_uid()
    if not chat_to_uid:
        print("state/incoming/ 没找到任何买家方消息")
        return

    orders = [load(args.order_id)] if args.order_id else list_all()
    changes = 0
    for order in orders:
        oid     = order.get("xianyu_order_id", "")
        chat_id = order.get("xianyu_chat_id", "")
        buyer   = order.setdefault("buyer", {})
        cur_uid = buyer.get("xianyu_uid", "") if isinstance(buyer, dict) else ""
        if cur_uid:
            continue
        candidate = chat_to_uid.get(chat_id, "")
        if not candidate:
            print(f"[{oid}] chat_id={chat_id!r}  → 没找到候选 uid")
            continue
        print(f"[{oid}] chat_id={chat_id}  → uid={candidate}{'  ✓写入' if args.apply else '  (dry-run)'}")
        if args.apply:
            buyer["xianyu_uid"] = candidate
            save(order)
            changes += 1

    if not args.apply:
        print(f"\n[dry-run] 加 --apply 真写入")
    else:
        print(f"\n已写入 {changes} 条")


if __name__ == "__main__":
    main()
