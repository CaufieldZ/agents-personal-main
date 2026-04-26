"""
把 TG 成功群 PNR 事件关联到订单。

用法：
  python3 commands/match_pnr.py                                            # 列出未关联事件
  python3 commands/match_pnr.py --pnr-file pnr_xxx.json --order-id <id>   # dry-run
  python3 commands/match_pnr.py --pnr-file pnr_xxx.json --order-id <id> --confirm
  python3 commands/match_pnr.py --pnr-file pnr_xxx.json --order-id <id> --pnr FGC4XU --confirm
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

_INCOMING = _ROOT / "state" / "incoming"

from lib.order_store import load, save, update_status


def _load_pnr_events(include_matched: bool) -> list[dict]:
    if not _INCOMING.exists():
        return []
    events = []
    for p in sorted(_INCOMING.glob("pnr_*.json")):
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
            ev["_path"] = str(p)
            ev["_filename"] = p.name
            if include_matched or not ev.get("order_id"):
                events.append(ev)
        except Exception:
            pass
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="关联 PNR 事件到订单")
    parser.add_argument("--pnr-file",  help="PNR 事件文件名（如 pnr_xxx.json）")
    parser.add_argument("--order-id",  help="订单 ID（xianyu_order_id）")
    parser.add_argument("--pnr",       help="手动指定 PNR 码（覆盖事件文本）")
    parser.add_argument("--all",       action="store_true", help="包含已关联事件")
    parser.add_argument("--confirm",   action="store_true", help="加此参数才真写入，否则只打印")
    args = parser.parse_args()

    # 列出模式
    if not args.pnr_file and not args.order_id:
        events = _load_pnr_events(include_matched=args.all)
        if not events:
            label = "PNR 事件" if args.all else "未关联 PNR 事件"
            print(f"没有{label}")
            return
        for ev in events:
            matched = f"  → 订单 {ev['order_id']}" if ev.get("order_id") else "  [未关联]"
            att = f"  附件 {len(ev['attachments'])} 张" if ev.get("attachments") else ""
            print(f"{ev['_filename']}{matched}{att}")
            print(f"  时间：{ev.get('ts', '')}  发件人：{ev.get('from_name', '')}")
            print(f"  文本：{ev.get('text', '')[:80]}")
        return

    if not args.pnr_file or not args.order_id:
        parser.print_help()
        sys.exit(1)

    # 找 PNR 文件
    pnr_path = _INCOMING / args.pnr_file
    if not pnr_path.exists():
        print(f"文件不存在：{pnr_path}")
        sys.exit(1)

    ev = json.loads(pnr_path.read_text(encoding="utf-8"))
    pnr_code = (args.pnr or ev.get("text") or "").strip()

    # 加载订单
    try:
        order = load(args.order_id)
    except FileNotFoundError:
        print(f"订单不存在：{args.order_id}")
        sys.exit(1)

    print("即将写入：")
    print(f"  订单：{args.order_id}")
    print(f"  PNR：{pnr_code}")
    if ev.get("attachments"):
        for att in ev["attachments"]:
            print(f"  附件：{att}")

    if not args.confirm:
        print("\n[dry-run] 未加 --confirm，不写入")
        return

    order.setdefault("fulfillment", {})
    order["fulfillment"]["supplier_pnr"]         = pnr_code
    order["fulfillment"]["supplier_attachments"] = ev.get("attachments") or []
    save(order)

    ev["order_id"]  = args.order_id
    ev["processed"] = True
    pnr_path.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")

    update_status(args.order_id, "已出票", f"PNR={pnr_code}")
    print(f"订单状态已推进：已出票")


if __name__ == "__main__":
    main()
