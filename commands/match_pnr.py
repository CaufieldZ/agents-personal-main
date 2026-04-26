"""
把上游成功 PNR 关联到订单。文本 PNR、二维码截图、两者都有 都支持。

用法：
  python3 commands/match_pnr.py                                                # 列未关联 PNR 事件
  python3 commands/match_pnr.py --pnr-file pnr_xxx.json --order-id <id> --confirm
  python3 commands/match_pnr.py --order-id <id> --pnr FGC4XU --confirm        # 纯文本 PNR
  python3 commands/match_pnr.py --order-id <id> --attachment qr.png --confirm  # 纯二维码
  python3 commands/match_pnr.py --order-id <id> --pnr X --attachment qr.png --confirm  # 都有
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

_INCOMING        = _ROOT / "state" / "incoming"
_ORDER_ATT_ROOT  = _ROOT / "state" / "attachments" / "orders"

from lib.order_store import load, save, update_status


def _load_pnr_events(include_matched: bool) -> list[dict]:
    if not _INCOMING.exists():
        return []
    events = []
    for p in sorted(_INCOMING.glob("pnr_*.json")):
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
            ev["_path"]     = str(p)
            ev["_filename"] = p.name
            if include_matched or not ev.get("order_id"):
                events.append(ev)
        except Exception:
            pass
    return events


def _copy_attachments(order_id: str, src_paths: list[str]) -> list[str]:
    """复制本地文件到 state/attachments/orders/<order_id>/，返回相对仓库根的路径列表。"""
    target_dir = _ORDER_ATT_ROOT / order_id
    target_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for src_str in src_paths:
        src = Path(src_str).expanduser()
        if not src.exists():
            raise FileNotFoundError(f"附件不存在：{src}")
        dst = target_dir / src.name
        if dst.exists() and dst.read_bytes() != src.read_bytes():
            stem, suffix, i = dst.stem, dst.suffix, 1
            while True:
                dst = target_dir / f"{stem}_{i}{suffix}"
                if not dst.exists():
                    break
                i += 1
        shutil.copy2(src, dst)
        out.append(str(dst.relative_to(_ROOT)))
    return out


def _build_note(pnr_code: str, n_att: int) -> str:
    if pnr_code and n_att:
        return f"PNR={pnr_code}，附件 {n_att} 张"
    if pnr_code:
        return f"PNR={pnr_code}"
    if n_att:
        return f"二维码附件 {n_att} 张"
    return ""


def _list_events(include_matched: bool) -> None:
    events = _load_pnr_events(include_matched=include_matched)
    if not events:
        label = "PNR 事件" if include_matched else "未关联 PNR 事件"
        print(f"没有{label}")
        return
    for ev in events:
        matched = f"  → 订单 {ev['order_id']}" if ev.get("order_id") else "  [未关联]"
        att = f"  附件 {len(ev['attachments'])} 张" if ev.get("attachments") else ""
        print(f"{ev['_filename']}{matched}{att}")
        print(f"  时间：{ev.get('ts', '')}  发件人：{ev.get('from_name', '')}")
        print(f"  文本：{ev.get('text', '')[:80]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="关联 PNR / 二维码到订单")
    parser.add_argument("--pnr-file",   help="PNR 事件文件名（如 pnr_xxx.json）")
    parser.add_argument("--order-id",   help="订单 ID（xianyu_order_id）")
    parser.add_argument("--pnr",        help="文本 PNR（覆盖事件文本）")
    parser.add_argument("--attachment", action="append", default=[],
                        help="本地附件文件路径，可重复；会复制到 state/attachments/orders/<order-id>/")
    parser.add_argument("--all",        action="store_true", help="列表模式包含已关联事件")
    parser.add_argument("--confirm",    action="store_true", help="加此参数才真写入")
    args = parser.parse_args()

    # 列表模式
    if not args.order_id and not args.pnr_file:
        _list_events(include_matched=args.all)
        return

    if not args.order_id:
        print("缺 --order-id")
        sys.exit(1)

    # 加载订单
    try:
        order = load(args.order_id)
    except FileNotFoundError:
        print(f"订单不存在：{args.order_id}")
        sys.exit(1)

    # 来源 1：PNR 事件文件
    ev = None
    ev_attachments: list[str] = []
    if args.pnr_file:
        pnr_path = _INCOMING / args.pnr_file
        if not pnr_path.exists():
            print(f"事件文件不存在：{pnr_path}")
            sys.exit(1)
        ev = json.loads(pnr_path.read_text(encoding="utf-8"))
        ev_attachments = ev.get("attachments") or []

    # 决定 PNR 文本：--pnr 优先，否则取事件 text
    pnr_code = (args.pnr if args.pnr is not None else (ev.get("text") if ev else "")).strip()

    # 来源 2：本地附件参数（与事件附件合并）
    local_attachments: list[str] = []
    if args.attachment:
        try:
            local_attachments = _copy_attachments(args.order_id, args.attachment)
        except FileNotFoundError as e:
            print(e)
            sys.exit(1)

    all_attachments = ev_attachments + local_attachments

    if not pnr_code and not all_attachments:
        print("既无 PNR 文本也无附件，没什么可写")
        sys.exit(1)

    note = _build_note(pnr_code, len(all_attachments))

    print("即将写入：")
    print(f"  订单：{args.order_id}")
    print(f"  PNR ：{pnr_code or '（无文本）'}")
    for a in all_attachments:
        print(f"  附件：{a}")
    print(f"  状态：→ 已出票  ({note})")

    if not args.confirm:
        print("\n[dry-run] 未加 --confirm，不写入")
        return

    ff = order.setdefault("fulfillment", {})
    if pnr_code:
        ff["supplier_pnr"] = pnr_code
    elif "supplier_pnr" not in ff:
        ff["supplier_pnr"] = ""
    existing = ff.get("supplier_attachments") or []
    ff["supplier_attachments"] = list(dict.fromkeys(existing + all_attachments))
    save(order)

    if ev is not None:
        ev["order_id"]  = args.order_id
        ev["processed"] = True
        (_INCOMING / args.pnr_file).write_text(
            json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    update_status(args.order_id, "已出票", note)
    print(f"订单状态已推进：已出票")


if __name__ == "__main__":
    main()
