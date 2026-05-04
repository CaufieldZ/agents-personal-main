#!/usr/bin/env python3
"""
列出钦钦未来 N 天该做的事(疫苗 + 体检)。

用法:
    python commands/parenting/upcoming.py            # 默认 90 天
    python commands/parenting/upcoming.py --days 180
    python commands/parenting/upcoming.py --all      # 全部未完成项

数据源: parenting/profile.json + parenting/schedule/{vaccines,checkups}.json
"""
import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "parenting" / "profile.json"
VAX = ROOT / "parenting" / "schedule" / "vaccines.json"
CHK = ROOT / "parenting" / "schedule" / "checkups.json"


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def add_months(d: date, months: int) -> date:
    """近似加月: 同日号,跨月用月末。"""
    y, m = d.year, d.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90, help="未来 N 天窗口(默认 90)")
    ap.add_argument("--all", action="store_true", help="忽略窗口,列全部未完成")
    args = ap.parse_args()

    profile = load(PROFILE)
    birth = parse_date(profile["birth_date"])
    today = date.today()
    horizon = today + timedelta(days=args.days)

    rows: list[tuple[date, str, str]] = []

    vax = load(VAX)
    for item in vax.get("upcoming", []):
        if item.get("done"):
            continue
        due = parse_date(item["due_date"]) if "due_date" in item else add_months(birth, item["due_age_months"])
        rows.append((due, "疫苗", f"{item['name']} 第 {item['dose']} 剂  ({item.get('note', '')})"))

    for item in vax.get("annual_or_seasonal", []):
        if item.get("done"):
            continue
        rows.append((today, "疫苗(季节性)", f"{item['name']}  ({item.get('note', '')})"))

    chk = load(CHK)
    for item in chk.get("items", []):
        if item.get("done"):
            continue
        due = add_months(birth, item["age_months"])
        if due < today - timedelta(days=30):
            continue
        rows.append((due, "体检", f"{item['age_months']} 月龄: " + ", ".join(item["items"])))

    rows.sort(key=lambda r: r[0])

    print(f"# 钦钦待办 (今天 {today},月龄 ≈ {(today - birth).days // 30})")
    print()

    shown = 0
    for due, kind, desc in rows:
        if not args.all and due > horizon:
            continue
        delta = (due - today).days
        flag = "  逾期" if delta < 0 else f"  {delta:+d} 天"
        print(f"{due}  [{kind:8s}] {desc}{flag}")
        shown += 1

    if shown == 0:
        print(f"未来 {args.days} 天内无待办。`--all` 看全部。")


if __name__ == "__main__":
    main()
