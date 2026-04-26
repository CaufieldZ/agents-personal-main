"""
向买家发送闲鱼私信。没有 --confirm 只 dry-run 打印，不发送。

用法：
  python3 commands/reply.py --chat-id 60975312198 --to-uid 2671936772 --text "你好"
  python3 commands/reply.py --chat-id 60975312198 --to-uid 2671936772 --text "你好" --confirm

  也可以用订单 ID 自动查 chat_id 和买家 uid（需订单里有 xianyu_chat_id 和 buyer.xianyu_uid）：
  python3 commands/reply.py --order-id ydedc_2026-04-26_hkg-tpe --text "已出票" --confirm
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.order_store import load


def _resolve(args: argparse.Namespace) -> tuple[str, str]:
    """返回 (chat_id, to_uid)"""
    if args.order_id:
        try:
            order = load(args.order_id)
        except FileNotFoundError:
            print(f"订单不存在：{args.order_id}")
            sys.exit(1)
        chat_id = order.get("xianyu_chat_id", "")
        to_uid  = order.get("buyer", {}).get("xianyu_uid", "") if isinstance(order.get("buyer"), dict) else ""
        if not chat_id or not to_uid:
            print("订单缺少 xianyu_chat_id 或 buyer.xianyu_uid，请手动指定 --chat-id 和 --to-uid")
            sys.exit(1)
        return chat_id, to_uid
    if not args.chat_id or not args.to_uid:
        print("需要提供 --chat-id 和 --to-uid，或者 --order-id")
        sys.exit(1)
    return args.chat_id, args.to_uid


def main() -> None:
    parser = argparse.ArgumentParser(description="向买家发送闲鱼私信")
    parser.add_argument("--order-id", help="从订单自动解析 chat_id 和 to_uid")
    parser.add_argument("--chat-id", help="会话 ID")
    parser.add_argument("--to-uid", help="买家 UID")
    parser.add_argument("--text", required=True, help="消息正文")
    parser.add_argument("--confirm", action="store_true", help="加此参数才真发，否则只打印")
    args = parser.parse_args()

    chat_id, to_uid = _resolve(args)

    print("即将发送：")
    print(f"  会话：{chat_id}  买家 UID：{to_uid}")
    print(f"  内容：{args.text}")

    if not args.confirm:
        print("\n[dry-run] 未加 --confirm，不发送")
        return

    from lib.xianyu_client import send_message
    try:
        send_message(chat_id, to_uid, args.text)
        print("发送成功")
    except Exception as e:
        print(f"发送失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
