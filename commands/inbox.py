"""
列出 state/incoming/ 里未处理的事件，按类型分组。

用法：
  python3 commands/inbox.py
  python3 commands/inbox.py --all       # 包含已处理
  python3 commands/inbox.py --mark-read # 列出后标记为已处理
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
_INCOMING = _ROOT / "state" / "incoming"

from lib import item_cache


def _load_events(pattern: str, include_processed: bool) -> list[dict]:
    if not _INCOMING.exists():
        return []
    events = []
    for p in sorted(_INCOMING.glob(pattern)):
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
            ev["_path"]     = str(p)
            ev["_filename"] = p.name
            if include_processed or not ev.get("processed"):
                events.append(ev)
        except Exception:
            pass
    return events


def _mark_processed(paths: list[str]) -> None:
    for path_str in paths:
        p = Path(path_str)
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
            ev["processed"] = True
            p.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="列出闲鱼和 TG 未处理事件")
    parser.add_argument("--all",       action="store_true", help="包含已处理事件")
    parser.add_argument("--mark-read", action="store_true", help="列出后标记为已处理")
    parser.add_argument("--no-titles", action="store_true", help="不查商品标题（更快，离线可用）")
    args = parser.parse_args()

    chat_events = _load_events("chat_*.json", args.all)
    pnr_events  = _load_events("pnr_*.json",  args.all)

    paths_to_mark: list[str] = []

    # ── 闲鱼聊天事件 ──────────────────────────────────────
    if chat_events:
        print("=== 闲鱼聊天 ===")
        grouped: dict[str, list] = defaultdict(list)
        for ev in chat_events:
            grouped[ev.get("chat_id", "unknown")].append(ev)

        for chat_id, evs in sorted(grouped.items()):
            buyer = next(
                (e.get("sender_name") for e in evs if e.get("direction") != "out"),
                evs[0].get("sender_name") or evs[0].get("sender_id", "")
            )
            buyer_uid = next(
                (e.get("sender_id") for e in evs if e.get("direction") != "out"),
                ""
            )
            item_id = evs[0].get("item_id", "")
            item_label = item_id
            if item_id and not args.no_titles:
                title = item_cache.get_title(item_id)
                if title:
                    item_label = f"{item_id}（{title}）"
            print(f"\n会话 {chat_id}  买家={buyer}（uid={buyer_uid}）  商品={item_label}  共 {len(evs)} 条")
            for ev in evs:
                mark      = "[已读]" if ev.get("processed") else "[新]  "
                ts        = ev.get("ts", "")[:16]
                tp        = ev.get("type", "")
                content   = ev.get("content", "")[:60]
                direction = ev.get("direction", "in")
                arrow     = "→ 你" if direction == "out" else "← 买家"
                print(f"  {mark} {ts}  {arrow}  [{tp}] {content}")
                paths_to_mark.append(ev["_path"])

    # ── TG PNR 事件 ───────────────────────────────────────
    if pnr_events:
        print("\n=== TG 成功群 PNR ===")
        for ev in pnr_events:
            matched = f"  → 订单 {ev['order_id']}" if ev.get("order_id") else "  [未关联]"
            mark    = "[已读]" if ev.get("processed") else "[新]  "
            att     = f"  附件 {len(ev['attachments'])} 张" if ev.get("attachments") else ""
            ts      = ev.get("ts", "")[:16]
            text    = ev.get("text", "")[:60]
            print(f"  {mark} {ts}  {ev['_filename']}{matched}{att}")
            print(f"         文本：{text}")
            paths_to_mark.append(ev["_path"])

    if not chat_events and not pnr_events:
        label = "事件" if args.all else "未处理事件"
        print(f"没有{label}")
        return

    if args.mark_read:
        _mark_processed(paths_to_mark)
        print(f"\n已标记 {len(paths_to_mark)} 条为已处理")


if __name__ == "__main__":
    main()
