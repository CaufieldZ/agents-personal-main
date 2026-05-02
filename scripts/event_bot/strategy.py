"""震荡区间接针策略——共享判定逻辑。

bot.py 和 backtest.py 都从这里 import，确保两边用同一份代码做检测，
避免 live 和回测漂移。本模块不依赖 config，参数通过函数/构造器传入；
不带任何 import 副作用（不设环境变量、不发网络请求）。
"""

import datetime as _dt
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class Candle:
    open: float; high: float; low: float; close: float; ts: int; vol: float = 0.0


@dataclass
class RangeStatus:
    consolidating: bool; high: float; low: float; width_pct: float; n: int


@dataclass
class WickEvent:
    direction: str       # 'down' = 下影线（做多） / 'up' = 上影线（做空）
    extreme: float
    breach_pct: float
    revert_sec: float    # 1m 模式下固定 0，仅保留字段兼容旧 Signal 结构


class RangeDetector:
    def __init__(self, lookback: int, max_width: float):
        self.lookback = lookback
        self.max_width = max_width
        self.buf: deque[Candle] = deque(maxlen=lookback)

    def add(self, c: Candle):
        self.buf.append(c)

    @property
    def ready(self) -> bool:
        return len(self.buf) >= self.lookback

    def analyze(self) -> RangeStatus:
        if not self.ready:
            return RangeStatus(False, 0, 0, 0, len(self.buf))
        items = list(self.buf)
        lows = sorted(c.low for c in items)
        highs = sorted(c.high for c in items)
        i_lo = len(lows) // 10
        i_hi = len(highs) * 9 // 10
        rlo = lows[i_lo]
        rhi = highs[i_hi]
        w = (rhi - rlo) / rlo
        return RangeStatus(w < self.max_width, rhi, rlo, w, len(items))


class WickDetector:
    """1m 蜡烛接针检测器。无状态、单根判定。"""

    def __init__(self, min_breach: float):
        self.min_breach = min_breach

    def detect(self, c: Candle, r: RangeStatus) -> Optional[WickEvent]:
        if not r.consolidating:
            return None
        # 下影针：穿透下沿且收盘回到区间内 → CALL
        if c.low < r.low * (1 - self.min_breach) and c.close >= r.low:
            breach = (r.low - c.low) / r.low
            return WickEvent('down', c.low, breach, 0)
        # 上影针：穿透上沿且收盘回到区间内 → PUT
        if c.high > r.high * (1 + self.min_breach) and c.close <= r.high:
            breach = (c.high - r.high) / r.high
            return WickEvent('up', c.high, breach, 0)
        return None


def momentum_ok(rdet: RangeDetector, max_slope: float) -> bool:
    """检查区间内归一化价格趋势斜率是否在允许范围。"""
    items = list(rdet.buf)
    if len(items) < 10:
        return True
    n = len(items)
    x_mean = (n - 1) / 2
    y_mean = sum(c.close for c in items) / n
    num = sum((i - x_mean) * (c.close - y_mean) for i, c in enumerate(items))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0 or y_mean == 0:
        return True
    slope = num / den / y_mean
    return abs(slope) < max_slope


# ─────────────────────────────────────────────────────────────
# 美股交易日历（北京时间过滤）
# 注意：节假日表只覆盖 2026 年。跨年回测前需补 2025/2027 数据。
# ─────────────────────────────────────────────────────────────

_US_HOLIDAYS = {
    _dt.date(2026, 1, 1),    # 元旦
    _dt.date(2026, 1, 19),   # 马丁·路德·金日
    _dt.date(2026, 2, 16),   # 总统日
    _dt.date(2026, 4, 3),    # 耶稣受难日
    _dt.date(2026, 5, 25),   # 阵亡将士纪念日
    _dt.date(2026, 6, 19),   # 六月节
    _dt.date(2026, 7, 3),    # 独立日提前
    _dt.date(2026, 9, 7),    # 劳动节
    _dt.date(2026, 11, 26),  # 感恩节
    _dt.date(2026, 12, 25),  # 圣诞节
}

_US_EARLY_CLOSE = {
    _dt.date(2026, 11, 27),  # 黑色星期五
    _dt.date(2026, 12, 24),  # 平安夜
}


def _is_us_trading_day(d: _dt.date) -> bool:
    if d.weekday() >= 5:
        return False
    if d in _US_HOLIDAYS:
        return False
    return True


def is_trading_hours_at(ts_ms: int, only_off_hours: bool = True,
                        block_start: int = 20, block_end: int = 4,
                        early_end: int = 1) -> bool:
    """指定北京时间戳（毫秒）是否允许交易。

    - only_off_hours=False 时永远返回 True
    - 否则：04:00-20:00 永远安全；20:00-04:00 看对应美股日是否开市
    """
    if not only_off_hours:
        return True

    now = _dt.datetime.fromtimestamp(ts_ms / 1000)
    today = now.date()
    hour = now.hour

    if block_end <= hour < block_start:
        return True

    if hour >= block_start:
        us_date = today
    else:
        us_date = today - _dt.timedelta(days=1)
        if us_date in _US_EARLY_CLOSE and hour >= early_end:
            return True

    return not _is_us_trading_day(us_date)


def is_trading_hours(only_off_hours: bool = True,
                     block_start: int = 20, block_end: int = 4) -> bool:
    """便捷包装：用当前时间。bot.py 主循环用这个。"""
    return is_trading_hours_at(int(time.time() * 1000),
                               only_off_hours=only_off_hours,
                               block_start=block_start, block_end=block_end)
