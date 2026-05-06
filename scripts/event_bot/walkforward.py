#!/usr/bin/env python3
"""Walk-forward 验证：避免过拟合的"考试"

把历史数据切两半：前一半"复习"（参数搜索），后一半"考试"（用搜出来的参数实跑）。
如果"考试"胜率 < 54%（break-even）就是过拟合，参数没价值；
如果还能保 55%+ 才说明参数真有效。

用法:
    python walkforward.py --days 14            # 前 7 天调参 + 后 7 天验证
    python walkforward.py --days 28            # 前 14 天调参 + 后 14 天验证
"""

import argparse
import json
from datetime import datetime
from itertools import product

import params as cfg          # 策略参数走 params（进 git）
from backtest import fetch_range, run_backtest, print_result, get_optimize_grid, INTERVAL_MIN


def split_in_half(candles):
    mid = len(candles) // 2
    return candles[:mid], candles[mid:]


def grid_search(candles, interval='1m'):
    """精简版网格搜索，直接从 backtest 拿统一 grid。"""
    grid = get_optimize_grid(interval)
    keys = list(grid.keys())
    best_result, best_params = None, None
    total = 1
    for v in grid.values():
        total *= len(v)
    print(f"  扫 {total} 套参数...", flush=True)
    tested = 0
    for values in product(*grid.values()):
        params = dict(zip(keys, values))
        result = run_backtest(candles, params, interval=interval)
        tested += 1
        if tested % 200 == 0:
            print(f"    {tested}/{total}", flush=True)
        if result.total < 5:
            continue
        if best_result is None or result.profit > best_result.profit:
            best_result = result
            best_params = params
    return best_params, best_result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--days', type=int, default=14, help='总天数（前一半调参，后一半验证）')
    p.add_argument('--interval', type=str, default='1m',
                   choices=list(INTERVAL_MIN.keys()), help='K线间隔 (默认 1m)')
    args = p.parse_args()

    print(f"=== Walk-Forward 验证 ({args.days} 天 {args.interval}，五五开切） ===\n")
    print(f"加载 BTCUSDT {args.days} 天 {args.interval} K 线...")
    candles = fetch_range(cfg.SYMBOL, args.interval, args.days)
    if len(candles) < 1000:
        print(f"[!] 数据不足: {len(candles)} 根")
        return
    print(f"获取 {len(candles)} 根  "
          f"({datetime.fromtimestamp(candles[0].ts/1000).strftime('%m-%d %H:%M')} ~ "
          f"{datetime.fromtimestamp(candles[-1].ts/1000).strftime('%m-%d %H:%M')})\n")

    train, test = split_in_half(candles)
    train_start = datetime.fromtimestamp(train[0].ts/1000).strftime('%m-%d')
    train_end = datetime.fromtimestamp(train[-1].ts/1000).strftime('%m-%d')
    test_start = datetime.fromtimestamp(test[0].ts/1000).strftime('%m-%d')
    test_end = datetime.fromtimestamp(test[-1].ts/1000).strftime('%m-%d')
    print(f"调参段（in-sample）: {train_start} ~ {train_end}  ({len(train)} 根)")
    print(f"验证段（out-of-sample）: {test_start} ~ {test_end}  ({len(test)} 根)\n")

    print("--- Step 1: 在调参段做网格搜索 ---")
    best_params, in_sample_result = grid_search(train, interval=args.interval)
    if not best_params:
        print("[!] 调参段没找到足够交易的参数组")
        return
    print()
    print_result(in_sample_result, "调参段最优结果（in-sample，可能过拟合）")

    print("\n--- Step 2: 拿这套参数去验证段实跑 ---")
    out_sample_result = run_backtest(test, best_params, interval=args.interval)
    print_result(out_sample_result, "验证段结果（out-of-sample，真实考试）")

    # ─── 对比与判断 ───
    in_wr = in_sample_result.win_rate * 100
    out_wr = out_sample_result.win_rate * 100
    in_pnl = in_sample_result.profit
    out_pnl = out_sample_result.profit
    drop = in_wr - out_wr

    print(f"\n{'='*55}")
    print("  对比")
    print(f"  {'─'*45}")
    print(f"  in-sample  : {in_sample_result.total:3d} 笔  "
          f"胜率 {in_wr:.1f}%  盈亏 {in_pnl:+.1f}U")
    print(f"  out-sample : {out_sample_result.total:3d} 笔  "
          f"胜率 {out_wr:.1f}%  盈亏 {out_pnl:+.1f}U")
    print(f"  胜率落差   : {drop:+.1f} pp")
    print(f"{'='*55}\n")

    # 结论
    print("结论:")
    if out_sample_result.total < 5:
        print("  ⚠️  验证段交易太少，结论不可信。建议拉长 --days")
    elif out_wr < 54:
        print(f"  ❌ 验证段胜率 {out_wr:.1f}% < 54%，是过拟合，这套参数不值得 apply")
    elif out_wr < 58:
        print(f"  ⚠️  验证段胜率 {out_wr:.1f}%，刚好在盈亏边缘。可以 apply 但要密切观察")
    else:
        print(f"  ✅ 验证段胜率 {out_wr:.1f}%，参数泛化能力可，可以 apply 上线模拟")

    print(f"\n  搜出的参数: {json.dumps(best_params, ensure_ascii=False)}")


if __name__ == '__main__':
    main()
