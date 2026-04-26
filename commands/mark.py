"""
手动推进订单状态。

用法：
  python3 commands/mark.py --order-id <id> --status 已收货
  python3 commands/mark.py --order-id <id> --status 已付款 --note "买家备注"
  python3 commands/mark.py --list-statuses
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.order_store import VALID_STATUSES, update_status


def main() -> None:
    parser = argparse.ArgumentParser(description="手动推进订单状态")
    parser.add_argument("--order-id", help="订单 ID（xianyu_order_id）")
    parser.add_argument("--status", help="目标状态")
    parser.add_argument("--note", default="", help="备注（可选）")
    parser.add_argument("--list-statuses", action="store_true", help="列出所有合法状态")
    args = parser.parse_args()

    if args.list_statuses:
        print("合法状态：")
        for s in sorted(VALID_STATUSES):
            print(f"  {s}")
        return

    if not args.order_id or not args.status:
        parser.print_help()
        sys.exit(1)

    try:
        order = update_status(args.order_id, args.status, args.note or None)
        print(f"订单 {args.order_id} 状态已更新为：{order['status']}")
        tl = order.get("timeline", [])
        if tl:
            last = tl[-1]
            print(f"  时间：{last['at']}" + (f"  备注：{last['note']}" if last.get("note") else ""))
    except FileNotFoundError:
        print(f"订单不存在：{args.order_id}")
        sys.exit(1)
    except ValueError as e:
        print(f"错误：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
