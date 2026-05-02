"""
把 PNR 回执发给买家（闲鱼私信）。没有 --confirm 只打印，不发送。

用法：
  python3 commands/send_receipt.py --order-id <id>
  python3 commands/send_receipt.py --order-id <id> --confirm
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.order_store import load, save, update_status

_TZ_CST = timezone(timedelta(hours=8))


def _receipt_text(order: dict) -> str:
    buyer    = order.get("buyer") or {}
    item     = order.get("item") or {}
    pnr      = (order.get("fulfillment") or {}).get("supplier_pnr", "")
    nick     = buyer.get("nick") or ""
    summary  = item.get("summary") or ""

    lines = [
        f"你好{' ' + nick if nick else ''}！",
        f"您的{summary}已出票，以下是您的出行凭证：",
        f"PNR：{pnr}",
        "如需协助值机、选座或有其他问题，请随时告知。",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="发 PNR 回执给买家")
    parser.add_argument("--order-id", required=True, help="订单 ID（xianyu_order_id）")
    parser.add_argument("--confirm",  action="store_true", help="加此参数才真发，否则只打印")
    args = parser.parse_args()

    try:
        order = load(args.order_id)
    except FileNotFoundError:
        print(f"订单不存在：{args.order_id}")
        sys.exit(1)

    fulfillment = order.get("fulfillment") or {}
    pnr = fulfillment.get("supplier_pnr", "").strip()
    if not pnr:
        print("订单尚无 PNR，先运行 commands/match_pnr.py 关联")
        sys.exit(1)

    buyer    = order.get("buyer") or {}
    chat_id  = order.get("xianyu_chat_id", "")
    to_uid   = buyer.get("xianyu_uid", "") if isinstance(buyer, dict) else ""

    if not chat_id or not to_uid:
        print("订单缺少 xianyu_chat_id 或 buyer.xianyu_uid，无法发消息")
        sys.exit(1)

    text = _receipt_text(order)
    attachments = fulfillment.get("supplier_attachments") or []

    print("即将发送：")
    print(f"  会话：{chat_id}  买家 UID：{to_uid}")
    print("─" * 40)
    print(text)
    print("─" * 40)
    if attachments:
        print(f"附件（{len(attachments)} 张）：")
        for att in attachments:
            print(f"  {att}")

    if not args.confirm:
        print("\n[dry-run] 未加 --confirm，不发送")
        return

    from lib.xianyu_client import send_message
    try:
        send_message(chat_id, to_uid, text)
        print("文字回执发送成功")
    except Exception as e:
        print(f"文字发送失败：{e}")
        sys.exit(1)

    order.setdefault("fulfillment", {})
    order["fulfillment"]["buyer_receipt_sent_at"] = datetime.now(_TZ_CST).isoformat(timespec="seconds")
    save(order)

    update_status(args.order_id, "已发回执", f"PNR={pnr}")
    print("订单状态已推进：已发回执")


if __name__ == "__main__":
    main()
