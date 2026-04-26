"""
查询/刷新 JPY → CNY 汇率。

用法：
  python3 scripts/show_fx.py              # 用缓存（24h 内）
  python3 scripts/show_fx.py --refresh    # 强制刷新
  python3 scripts/show_fx.py --jpy 13870  # 顺便换算一笔
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from lib.fx import _BUFFER, _TTL_HOURS, _get_payload, get_jpy_to_cny


def main() -> None:
    parser = argparse.ArgumentParser(description="查询 JPY→CNY 汇率")
    parser.add_argument("--refresh", action="store_true", help="强制刷新缓存")
    parser.add_argument("--jpy", type=float, help="把这笔 JPY 换算成 CNY")
    args = parser.parse_args()

    payload = _get_payload(force_refresh=args.refresh)
    mid     = payload["jpy_cny_mid"]
    rate    = mid * _BUFFER

    fetched = datetime.fromisoformat(payload["fetched_at"])
    age_h   = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600

    print(f"中间价：1 JPY = {mid:.6f} CNY  (来源 {payload['source']}, {payload.get('source_date', '')})")
    print(f"报价用：1 JPY = {rate:.6f} CNY  (×{_BUFFER} 缓冲)")
    print(f"缓存：{fetched.astimezone().strftime('%Y-%m-%d %H:%M %Z')}  ({age_h:.1f}h 前 / TTL {_TTL_HOURS}h)")

    if args.jpy:
        cny = args.jpy * rate
        print(f"\n¥{args.jpy:.0f} JPY  →  ¥{cny:.2f} CNY  →  报价 ¥{cny * 0.75:.0f}（×0.75）")


if __name__ == "__main__":
    main()
