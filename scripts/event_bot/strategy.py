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
    pos_pct: float = 0.0  # wick 极值在区间内归一化位置：0=区间底, 1=区间顶


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
    """1m 蜡烛接针检测器。无状态、单根判定。

    breach_ratio: 穿透幅度需 ≥ 区间宽度 × ratio（相对阈值，跨波动率环境一致）
    edge_zone: wick 极值必须落在区间边缘 [0, edge_zone]∪[1-edge_zone, 1]
               才出信号。1.0 = 全区间允许（关闭过滤，向后兼容）；
               0.20 = 仅区间底/顶 20% 内的接针才算
    """

    def __init__(self, breach_ratio: float, edge_zone: float = 1.0):
        self.breach_ratio = breach_ratio
        self.edge_zone = edge_zone

    def detect(self, c: Candle, r: RangeStatus) -> Optional[WickEvent]:
        if not r.consolidating:
            return None
        min_breach = r.width_pct * self.breach_ratio
        width = r.high - r.low
        if c.low < r.low * (1 - min_breach) and c.close >= r.low:
            breach = (r.low - c.low) / r.low
            # close 在区间内归一化位置；clamp 到 [0,1]
            pos = (c.close - r.low) / width if width > 0 else 0.0
            pos = max(0.0, min(1.0, pos))
            if pos > self.edge_zone:
                return None
            return WickEvent('down', c.low, breach, 0, pos)
        if c.high > r.high * (1 + min_breach) and c.close <= r.high:
            breach = (c.high - r.high) / r.high
            pos = (c.close - r.low) / width if width > 0 else 1.0
            pos = max(0.0, min(1.0, pos))
            if pos < 1 - self.edge_zone:
                return None
            return WickEvent('up', c.high, breach, 0, pos)
        return None


def volume_ok(c: Candle, recent: list, min_ratio: float) -> bool:
    """当前 candle 的成交量 ≥ recent 平均的 min_ratio 倍。

    无 vol 数据(回测旧数据)或 recent 为空时放行,避免误杀。
    """
    if not recent or min_ratio <= 0:
        return True
    avg = sum(x.vol for x in recent) / len(recent)
    if avg <= 0:
        return True
    return c.vol >= avg * min_ratio


def momentum_slope(rdet: RangeDetector) -> Optional[float]:
    """计算区间内归一化价格趋势斜率，数据不足返回 None。"""
    items = list(rdet.buf)
    if len(items) < 10:
        return None
    n = len(items)
    x_mean = (n - 1) / 2
    y_mean = sum(c.close for c in items) / n
    num = sum((i - x_mean) * (c.close - y_mean) for i, c in enumerate(items))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0 or y_mean == 0:
        return None
    return num / den / y_mean


def momentum_ok(rdet: RangeDetector, max_slope: float) -> bool:
    """检查区间内归一化价格趋势斜率是否在允许范围。"""
    s = momentum_slope(rdet)
    if s is None:
        return True
    return abs(s) < max_slope


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
