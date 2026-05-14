"""K 线数据本地缓存层。

按 UTC 日切片：data/binance_cache/{SYMBOL}_{interval}_{YYYY-MM-DD}.jsonl
仅缓存过去日期（today 不缓存，避免未收盘 K 线污染）。

调用方：backtest.py / walkforward.py 间接通过 fetch_range 用之。bot.py 不引用。
"""
import json
import urllib.request
from datetime import date as date_cls, datetime, time as time_cls, timedelta, timezone
from pathlib import Path

from strategy import Candle

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "binance_cache"


def _cache_path(symbol: str, interval: str, d: date_cls) -> Path:
    return CACHE_DIR / f"{symbol.upper()}_{interval}_{d.isoformat()}.jsonl"


def _is_past_day(d: date_cls) -> bool:
    return d < datetime.now(timezone.utc).date()


def _fetch_day_from_api(symbol: str, interval: str, d: date_cls) -> list[Candle]:
    """从 Binance API 拉一整天的 K 线（UTC 00:00 - 23:59:59.999）"""
    start_ms = int(datetime.combine(d, time_cls.min, tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.combine(d, time_cls.max, tzinfo=timezone.utc).timestamp() * 1000)
    out = []
    cursor = start_ms
    while cursor <= end_ms:
        url = (f"https://api.binance.com/api/v3/klines?"
               f"symbol={symbol.upper()}&interval={interval}"
               f"&startTime={cursor}&endTime={end_ms}&limit=1000")
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"[!] 缓存层拉取 {symbol} {interval} {d} 失败: {e}")
            break
        if not data:
            break
        for k in data:
            out.append(Candle(
                float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                k[0], float(k[5]),
            ))
        if len(data) < 1000:
            break
        cursor = data[-1][0] + 1
    return out


def _write_jsonl(path: Path, candles: list[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, 'w') as f:
        for c in candles:
            f.write(json.dumps({
                'ts': c.ts, 'open': c.open, 'high': c.high,
                'low': c.low, 'close': c.close, 'vol': c.vol,
            }) + '\n')
    tmp.replace(path)


def _read_jsonl(path: Path) -> list[Candle]:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(Candle(
                d['open'], d['high'], d['low'], d['close'],
                d['ts'], d.get('vol', 0.0),
            ))
    return out


def get_day_klines(symbol: str, interval: str, d: date_cls) -> list[Candle]:
    """拿一天的 K 线。过去日期走缓存；今天直接 API 不写盘。"""
    if _is_past_day(d):
        p = _cache_path(symbol, interval, d)
        if p.exists():
            return _read_jsonl(p)
        candles = _fetch_day_from_api(symbol, interval, d)
        if candles:
            _write_jsonl(p, candles)
        return candles
    return _fetch_day_from_api(symbol, interval, d)
