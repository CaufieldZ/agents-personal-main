#!/usr/bin/env python3
"""震荡区间接针策略回测 + 参数优化。

用 1 分钟 K 线历史数据回测。复用 strategy.py 的 RangeDetector / WickDetector /
momentum_ok / is_trading_hours_at，确保和 live 用同一份判定逻辑。

Entry 价用 candles[i+1].open（≈ 触发后下一秒指数价，对齐 Binance 事件合约新规）。
"""

import json
import os
import time
import urllib.request
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Optional

import params as cfg          # 策略参数走 params（进 git）
import config as _secrets     # token / PROXY 走 config（gitignored）
from strategy import (
    Candle, RangeDetector, WickDetector,
    momentum_ok, volume_ok, is_trading_hours_at,
)

os.environ['HTTPS_PROXY'] = _secrets.PROXY or os.environ.get('HTTPS_PROXY', '')


# ═══════════════════════════════════════════════════════════
# 数据结构（Candle 来自 strategy.py）
# ═══════════════════════════════════════════════════════════

@dataclass
class Trade:
    entry_time: datetime
    exit_time: datetime
    direction: str      # Long / Short
    entry_price: float
    exit_price: float
    won: bool
    pnl: float

@dataclass
class BacktestResult:
    total: int = 0
    wins: int = 0
    losses: int = 0
    profit: float = 0.0
    trades: list[Trade] = field(default_factory=list)
    params: dict = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total if self.total > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.profit / self.total if self.total > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        gross_win = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        return gross_win / gross_loss if gross_loss > 0 else float('inf')


# ═══════════════════════════════════════════════════════════
# 数据获取
# ═══════════════════════════════════════════════════════════

INTERVAL_MIN = {'1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30, '1h': 60}


def fetch_klines(symbol: str, interval: str, limit: int = 1000,
                 end_time: Optional[int] = None) -> list[Candle]:
    """从 Binance REST 拉 K 线"""
    url = (f"https://api.binance.com/api/v3/klines?"
           f"symbol={symbol.upper()}&interval={interval}&limit={limit}")
    if end_time:
        url += f"&endTime={end_time}"

    candles = []
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        for k in data:
            candles.append(Candle(
                float(k[1]), float(k[2]), float(k[3]), float(k[4]), k[0],
                float(k[5])
            ))
    except Exception as e:
        print(f"[!] 获取 K 线失败: {e}")
    return candles


def fetch_range(symbol: str, interval: str, days: int) -> list[Candle]:
    """分批拉取多天历史数据"""
    bars_per_day = 1440 // INTERVAL_MIN[interval]
    all_candles = []
    now_ms = int(time.time() * 1000)
    remaining = days
    end = now_ms

    while remaining > 0:
        batch = fetch_klines(symbol, interval, limit=min(1000, remaining * bars_per_day), end_time=end)
        if not batch:
            break
        all_candles = batch + all_candles
        end = batch[0].ts - 1
        remaining = days - len(all_candles) // bars_per_day
        if len(batch) < min(500, bars_per_day):
            break
        time.sleep(0.2)

    # 去重 + 排序
    seen = set()
    unique = []
    for c in all_candles:
        if c.ts not in seen:
            seen.add(c.ts)
            unique.append(c)
    unique.sort(key=lambda c: c.ts)
    return unique


# ═══════════════════════════════════════════════════════════
# 回测引擎
# ═══════════════════════════════════════════════════════════

def run_backtest(candles: list[Candle], params: dict, interval: str = '1m') -> BacktestResult:
    """K 线回测，复用 strategy.py 的判定逻辑。

    Entry = candles[i+1].open（≈ 触发后下一秒指数价）
    Exit  = candles[i+1+contract_bars].close,contract_bars 根据 interval 换算
    """
    interval_min = INTERVAL_MIN[interval]
    rlookback = params.get('RANGE_LOOKBACK', cfg.RANGE_LOOKBACK)
    max_width = params.get('RANGE_MAX_WIDTH', cfg.RANGE_MAX_WIDTH)
    breach_ratio = params.get('WICK_BREACH_RATIO', cfg.WICK_BREACH_RATIO)
    max_slope = params.get('MOMENTUM_MAX_SLOPE', cfg.MOMENTUM_MAX_SLOPE)
    vol_min = params.get('VOLUME_MIN_RATIO', cfg.VOLUME_MIN_RATIO)
    cooldown = params.get('SIGNAL_COOLDOWN', cfg.SIGNAL_COOLDOWN)
    contract_min = params.get('CONTRACT_DURATION', cfg.CONTRACT_DURATION)
    amount = params.get('AMOUNT', cfg.AMOUNT)
    only_off = params.get('TRADE_ONLY_OFF_HOURS', cfg.TRADE_ONLY_OFF_HOURS)
    block_start = params.get('TRADE_END_HOUR', cfg.TRADE_END_HOUR)
    block_end = params.get('TRADE_START_HOUR', cfg.TRADE_START_HOUR)

    rdet = RangeDetector(lookback=rlookback, max_width=max_width)
    wdet = WickDetector(breach_ratio=breach_ratio)

    result = BacktestResult(params=params)
    last_signal_ts = 0

    for i, c in enumerate(candles):
        rdet.add(c)
        if not rdet.ready:
            continue

        r = rdet.analyze()
        if not r.consolidating:
            continue
        if not is_trading_hours_at(c.ts, only_off_hours=only_off,
                                   block_start=block_start, block_end=block_end):
            continue
        if not momentum_ok(rdet, max_slope):
            continue
        if c.ts / 1000 - last_signal_ts < cooldown:
            continue

        w = wdet.detect(c, r)
        if w is None:
            continue
        if not volume_ok(c, list(rdet.buf)[:-1], vol_min):
            continue
        if i + 1 >= len(candles):
            continue

        direction = 'Long' if w.direction == 'down' else 'Short'
        entry_price = candles[i + 1].open
        contract_bars = max(1, contract_min // interval_min)
        exit_idx = min(i + 1 + contract_bars, len(candles) - 1)
        exit_price = candles[exit_idx].close

        if direction == 'Long':
            won = exit_price > entry_price
        else:
            won = exit_price < entry_price

        pnl = amount * 0.85 if won else -amount
        result.total += 1
        if won:
            result.wins += 1
        else:
            result.losses += 1
        result.profit += pnl
        result.trades.append(Trade(
            entry_time=datetime.fromtimestamp(candles[i + 1].ts / 1000),
            exit_time=datetime.fromtimestamp(candles[exit_idx].ts / 1000),
            direction=direction, entry_price=entry_price,
            exit_price=exit_price, won=won, pnl=pnl
        ))
        last_signal_ts = c.ts / 1000

    return result


# ═══════════════════════════════════════════════════════════
# 参数优化
# ═══════════════════════════════════════════════════════════

def get_optimize_grid(interval: str) -> dict:
    """按 K 线周期返回网格搜索参数空间。"""
    if interval == '5m':
        return {
            'RANGE_LOOKBACK': [12, 18, 24, 36],
            'RANGE_MAX_WIDTH': [0.006, 0.008, 0.010, 0.012, 0.015],
            'WICK_BREACH_RATIO': [0.05, 0.10, 0.15, 0.20],
            'MOMENTUM_MAX_SLOPE': [0.0002, 0.0003, 0.0005, 0.001],
            'VOLUME_MIN_RATIO': [0.0],
            'SIGNAL_COOLDOWN': [0],
            'CONTRACT_DURATION': [10, 30, 60],
        }
    return {
        'RANGE_LOOKBACK': [20, 30, 40],
        'RANGE_MAX_WIDTH': [0.006, 0.008, 0.010, 0.012, 0.015],
        'WICK_BREACH_RATIO': [0.05, 0.10, 0.15, 0.20],
        'MOMENTUM_MAX_SLOPE': [0.0002, 0.0003, 0.0005, 0.001],
        'VOLUME_MIN_RATIO': [1.0, 1.2, 1.5, 2.0],
        'SIGNAL_COOLDOWN': [60, 120, 300],
        'CONTRACT_DURATION': [10, 30, 60],
    }


def optimize(candles: list[Candle], interval: str = '1m') -> dict:
    """网格搜索最优参数"""
    # Binance 事件合约只支持 10/30/60/1440 min
    grid = get_optimize_grid(interval)

    keys = list(grid.keys())
    best_result = None
    best_params = None
    total_combos = 1
    for v in grid.values():
        total_combos *= len(v)

    print(f"参数组合数: {total_combos}")
    tested = 0

    for values in product(*grid.values()):
        params = dict(zip(keys, values))
        result = run_backtest(candles, params, interval=interval)
        tested += 1

        if tested % 50 == 0 or tested == 1:
            print(f"\r  进度: {tested}/{total_combos}  "
                  f"当前最优 胜率={best_result.win_rate*100:.1f}%  "
                  f"盈利={best_result.profit:.1f}U" if best_result else "  开始...",
                  end='', flush=True)

        if result.total < 5:
            continue  # 样本太少

        if best_result is None or result.profit > best_result.profit:
            best_result = result
            best_params = params

    print(f"\r  完成: {tested}/{total_combos} 组合\n")
    return best_params, best_result


# ═══════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════

def print_result(r: BacktestResult, title: str = "回测结果"):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"  {'─'*45}")
    print(f"  参数: {json.dumps(r.params, ensure_ascii=False)}")
    print(f"  交易次数: {r.total}")
    print(f"  胜率: {r.win_rate*100:.1f}%  ({r.wins}W / {r.losses}L)")
    print(f"  累计盈亏: {r.profit:+.2f}U")
    print(f"  平均每笔: {r.avg_pnl:+.2f}U")
    if r.profit_factor != float('inf'):
        print(f"  盈亏比: {r.profit_factor:.2f}")
    print(f"{'='*55}\n")

    if r.total > 0 and r.total <= 30:
        for t in r.trades:
            mark = '✓' if t.won else '✗'
            print(f"  {mark} {t.entry_time.strftime('%m-%d %H:%M')} {t.direction:6s}  "
                  f"{t.entry_price:.1f} → {t.exit_price:.1f}  {t.pnl:+.2f}U")


def update_config(params: dict, dry_run: bool = True):
    """将最优参数写回 params.py（进 git，commit + push 后家里 TG /pull 即可应用）"""
    config_path = Path(__file__).parent / 'params.py'
    lines = config_path.read_text().split('\n')

    mapping = {
        'RANGE_LOOKBACK': 'RANGE_LOOKBACK',
        'RANGE_MAX_WIDTH': 'RANGE_MAX_WIDTH',
        'WICK_BREACH_RATIO': 'WICK_BREACH_RATIO',
        'MOMENTUM_MAX_SLOPE': 'MOMENTUM_MAX_SLOPE',
        'VOLUME_MIN_RATIO': 'VOLUME_MIN_RATIO',
        'SIGNAL_COOLDOWN': 'SIGNAL_COOLDOWN',
        'CONTRACT_DURATION': 'CONTRACT_DURATION',
    }

    changed = {}
    new_lines = []
    for line in lines:
        replaced = False
        for cfg_key, bt_key in mapping.items():
            if bt_key in params and line.strip().startswith(cfg_key + ' '):
                val = params[bt_key]
                if isinstance(val, float):
                    val_str = f"{val:.4f}"
                else:
                    val_str = str(val)
                new_lines.append(f"{cfg_key} = {val_str}")
                changed[cfg_key] = val_str
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    if dry_run:
        print("[dry-run] 将写入以下参数:")
        for k, v in changed.items():
            print(f"  {k} = {v}")
        print()
    else:
        config_path.write_text('\n'.join(new_lines))
        print("已更新 params.py")
        for k, v in changed.items():
            print(f"  {k} = {v}")


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--days', type=int, default=7, help='回测天数 (默认 7)')
    p.add_argument('--interval', type=str, default='1m',
                   choices=list(INTERVAL_MIN.keys()), help='K线间隔 (默认 1m)')
    p.add_argument('--optimize', action='store_true', help='网格搜索最优参数')
    p.add_argument('--apply', action='store_true', help='将最优参数写入 config.py')
    args = p.parse_args()

    print(f"加载 {cfg.SYMBOL.upper()} {args.interval} K 线 (最近 {args.days} 天)...")
    candles = fetch_range(cfg.SYMBOL, args.interval, args.days)
    print(f"获取 {len(candles)} 根 K 线  "
          f"({datetime.fromtimestamp(candles[0].ts/1000).strftime('%m-%d %H:%M')} ~ "
          f"{datetime.fromtimestamp(candles[-1].ts/1000).strftime('%m-%d %H:%M')})")

    if args.optimize:
        print("\n网格搜索最优参数...")
        best_params, best_result = optimize(candles, interval=args.interval)
        if best_params:
            print_result(best_result, "最优参数回测")
            update_config(best_params, dry_run=not args.apply)
        else:
            print("[!] 未找到足够交易的参数组合")
    else:
        # 默认参数回测
        params = {k: getattr(cfg, k) for k in
                  ['RANGE_LOOKBACK', 'RANGE_MAX_WIDTH', 'WICK_BREACH_RATIO',
                   'MOMENTUM_MAX_SLOPE', 'VOLUME_MIN_RATIO',
                   'SIGNAL_COOLDOWN', 'CONTRACT_DURATION', 'AMOUNT']}
        result = run_backtest(candles, params, interval=args.interval)
        print_result(result, "当前参数回测")
        if result.total > 0 and result.profit < 0:
            print("提示: 当前参数亏损，建议 --optimize 搜索更优参数\n")
