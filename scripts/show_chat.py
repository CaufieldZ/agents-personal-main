"""
查看指定会话的历史聊天记录。

用法：
  python scripts/show_chat.py --chat-id 60811629304
  python scripts/show_chat.py --order-id wwwwwyiyi_2026-05-04_tokyo-kyoto_rail
"""
import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.xianyu_client import fetch_chat_history
from lib.order_store import load


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--chat-id", help="闲鱼会话 ID")
    g.add_argument("--order-id", help="订单 ID（自动取 xianyu_chat_id）")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    if args.order_id:
        order = load(args.order_id)
        chat_id = order.get("xianyu_chat_id", "")
        if not chat_id:
            print(f"订单 {args.order_id} 没有 xianyu_chat_id", file=sys.stderr)
            sys.exit(1)
    else:
        chat_id = args.chat_id

    print(f"拉取会话 {chat_id} 历史消息…")
    msgs = fetch_chat_history(chat_id, timeout=args.timeout)
    if not msgs:
        print("（无消息或会话不存在）")
        return

    for m in msgs:
        direction = m["direction"]
        name = m["sender_name"] or m["sender_uid"]
        text = m["text"]
        print(f"  {direction}  [{name}]  {text}")


if __name__ == "__main__":
    main()
