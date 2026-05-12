#!/usr/bin/env python3
"""震荡区间接针策略——BTC 实时监测 + 接针信号输出"""

import asyncio
import fcntl
import hashlib
import hmac
import json
import os
import socket
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import urllib.parse
import urllib.request

try:
    import websockets
except ImportError:
    print("pip install websockets")
    sys.exit(1)

from config import *           # token / proxy（gitignored）
from params import *           # 策略 / 风控参数（进 git，跨机同步，覆盖 config 同名字段）
from strategy import (
    Candle, RangeStatus, WickEvent,
    RangeDetector, WickDetector,
    momentum_ok, momentum_slope, volume_ok, is_trading_hours, is_trading_hours_at,
)

_CONF_RANK = {'低': 0, '中': 1, '高': 2}

# 启动检查：config.py 里如果还有策略参数，提示用户清理
import config as _cfg_mod
_PARAMS_FIELDS = {'SYMBOL', 'KLINE_INTERVAL', 'RANGE_LOOKBACK', 'RANGE_MAX_WIDTH',
                  'WICK_MIN_BREACH', 'WICK_BREACH_RATIO', 'VOLUME_MIN_RATIO',
                  'MOMENTUM_MAX_SLOPE', 'SIGNAL_COOLDOWN', 'MIN_CONFIDENCE',
                  'CONTRACT_DURATION', 'TRADE_ONLY_OFF_HOURS', 'TRADE_START_HOUR',
                  'TRADE_END_HOUR', 'AMOUNT', 'RISK_MAX_PER_HOUR',
                  'RISK_MAX_CONSEC_LOSS', 'RISK_REFLECT_CONSEC', 'RISK_LOSS_PAUSE_MIN',
                  'RISK_DAILY_LOSS_CAP', 'BINANCEELF_URL', 'TIME_TYPE_MAP',
                  'TIME_TYPE', 'LOG_FILE'}
_LEGACY_IN_CONFIG = sorted(f for f in _PARAMS_FIELDS if hasattr(_cfg_mod, f))

# 代理配置
if PROXY:
    os.environ['HTTP_PROXY'] = PROXY
    os.environ['HTTPS_PROXY'] = PROXY
    os.environ['http_proxy'] = PROXY
    os.environ['https_proxy'] = PROXY
    proxy_handler = urllib.request.ProxyHandler({'https': PROXY})
    urllib.request.install_opener(urllib.request.build_opener(proxy_handler))

# ═══════════════════════════════════════════════════════════
# 数据结构（仅 Signal 留在这里，其他在 strategy.py）
# ═══════════════════════════════════════════════════════════

@dataclass
class Signal:
    direction: str       # 'CALL' 看涨 / 'PUT' 看跌
    price: float
    range_high: float; range_low: float
    wick_pct: float; revert_sec: float
    confidence: str      # 高 / 中 / 低
    note: str
    ts: float

# ═══════════════════════════════════════════════════════════
# 信号生成
# ═══════════════════════════════════════════════════════════

class SignalEngine:
    def __init__(self):
        self._last_ts = 0.0
        self.history: list[Signal] = []

    def process(self, r: RangeStatus, w: WickEvent, price: float) -> Optional[Signal]:
        now = time.time()
        if now - self._last_ts < SIGNAL_COOLDOWN:
            return None

        direction = 'CALL' if w.direction == 'down' else 'PUT'
        conf = self._confidence(r, w)
        side_cn = '下影' if w.direction == 'down' else '上影'
        note = f"{side_cn}穿透 {w.breach_pct*100:.2f}%"

        sig = Signal(direction, price, r.high, r.low,
                     w.breach_pct, w.revert_sec, conf, note, now)
        self._last_ts = now
        self.history.append(sig)
        return sig

    def _confidence(self, r: RangeStatus, w: WickEvent) -> str:
        # 1m 模式无 revert 维度，剩余两维重新分配权重
        # breach 占区间宽度的比例越大置信度越高（3 倍阈值视为饱和）
        s = 0.0
        s += (1 - r.width_pct / RANGE_MAX_WIDTH) * 0.4
        breach_to_width = w.breach_pct / r.width_pct if r.width_pct > 0 else 0
        s += min(breach_to_width / (WICK_BREACH_RATIO * 3), 1) * 0.6
        return '高' if s >= 0.7 else '中' if s >= 0.4 else '低'

# ═══════════════════════════════════════════════════════════
# 行情流
# ═══════════════════════════════════════════════════════════

class BinanceStream:
    def __init__(self):
        sym = SYMBOL.lower()
        self.kline_stream = f"{sym}@kline_{KLINE_INTERVAL}"
        self.ws_url = f"wss://stream.binance.com:9443/stream?streams={self.kline_stream}/{sym}@kline_1s"
        self.rest_url = (f"https://api.binance.com/api/v3/klines?symbol={SYMBOL.upper()}"
                         f"&interval={KLINE_INTERVAL}&limit={RANGE_LOOKBACK + 10}")
        self._ws = None
        self._run = False
        self.on_kline = None    # 主周期 K 线收盘回调
        self.on_1s = None       # 1s 流（用于结算 + 延迟下单对齐"下一秒指数价"）
        self.on_status = None

    def test_connectivity(self) -> bool:
        """测试 Binance API 连通性"""
        try:
            req = urllib.request.Request("https://api.binance.com/api/v3/ping")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200 and resp.read() == b'{}'
        except Exception as e:
            print(f"[!] 连通性测试失败: {e}")
            if not PROXY:
                print("[!] 提示: 国内网络需配置代理，编辑 config.py 设置 PROXY")
            return False

    def fetch_history(self) -> list[Candle]:
        candles = []
        try:
            req = urllib.request.Request(self.rest_url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            for k in data:
                candles.append(Candle(float(k[1]), float(k[2]), float(k[3]), float(k[4]), k[0], float(k[5])))
        except Exception as e:
            print(f"[!] REST 获取历史失败: {e}")
        return candles

    async def start(self):
        self._run = True
        while self._run:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=30,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    try:
                        sock = ws.transport.get_extra_info('socket')
                        if sock:
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                            sock.setsockopt(socket.IPPROTO_TCP, 0x10, 120)
                            sock.setsockopt(socket.IPPROTO_TCP, 0x101, 30)
                            sock.setsockopt(socket.IPPROTO_TCP, 0x102, 3)
                    except Exception:
                        pass
                    self._emit_status("connected")
                    async for msg in ws:
                        if not self._run:
                            break
                        self._dispatch(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._emit_status(f"disconnected ({e})")
                if self._run:
                    await asyncio.sleep(3)

    def _dispatch(self, msg: str):
        try:
            d = json.loads(msg)
            k = d.get('data', {}).get('k', {})
            if not k:
                return
            c = Candle(float(k['o']), float(k['h']), float(k['l']), float(k['c']),
                       k['t'], float(k.get('v', 0)))
            stream = d.get('stream', '')
            if stream.endswith(f"@kline_{KLINE_INTERVAL}") and k.get('x') and self.on_kline:
                self.on_kline(c)
            elif stream.endswith("@kline_1s") and self.on_1s:
                self.on_1s(c)
        except Exception:
            pass

    def _emit_status(self, s: str):
        if self.on_status:
            self.on_status(s)

    async def stop(self):
        self._run = False
        if self._ws:
            await self._ws.close()

# ═══════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════

if sys.stdout.isatty():
    BOLD = '\033[1m'; RED = '\033[91m'; GREEN = '\033[92m'
    YELLOW = '\033[93m'; CYAN = '\033[96m'; RST = '\033[0m'
else:
    BOLD = RED = GREEN = YELLOW = CYAN = RST = ''

def fmt_signal(sig: Signal):
    arrow = f"{GREEN}📈 CALL 看涨{RST}" if sig.direction == 'CALL' else f"{RED}📉 PUT 看跌{RST}"
    cc = {'高': GREEN, '中': YELLOW, '低': RED}
    ts = datetime.fromtimestamp(sig.ts).strftime('%H:%M:%S')
    print(f"\n{BOLD}{'='*55}{RST}")
    print(f"  {BOLD}🚨 接针信号  {arrow}")
    print(f"  {'─'*45}")
    print(f"  时间: {ts}    当前价: {sig.price:.1f}")
    print(f"  震荡区间: {sig.range_low:.1f} - {sig.range_high:.1f}  "
          f"(宽 {(sig.range_high/sig.range_low-1)*100:.2f}%)")
    print(f"  穿透幅度: {sig.wick_pct*100:.2f}%")
    print(f"  置信度: {cc.get(sig.confidence, RST)}{sig.confidence}{RST}    备注: {sig.note}")
    print(f"{BOLD}{'='*55}{RST}\n")

def fmt_status(price: float, r: RangeStatus, n_sig: int, executor=None, balance=None):
    ts = datetime.now().strftime('%H:%M:%S')
    if r.consolidating:
        rng = f"{CYAN}震荡 [{r.low:.1f} - {r.high:.1f}] {r.width_pct*100:.2f}%{RST}"
    else:
        rng = f"非震荡 ({r.width_pct*100:.2f}%)"
    if TRADE_ONLY_OFF_HOURS:
        rng += f" {'🟢' if is_trading_hours() else '🔴'}"
    extra = ""
    if executor:
        w = executor.wins; l = executor.losses; t = executor.total
        if t > 0:
            extra += f" | {GREEN}{w}{RST}/{t} {executor.win_rate*100:.0f}%"
            if executor.profit >= 0:
                extra += f" {GREEN}+{executor.profit:.1f}U{RST}"
            else:
                extra += f" {RED}{executor.profit:.1f}U{RST}"
        if executor.pending_count > 0:
            extra += f" ⏳{executor.pending_count}"
        if not AUTO_TRADE and t > 0:
            extra += f" {YELLOW}(模拟){RST}"
    if balance and balance.usdt > 0:
        extra += f" | {CYAN}{balance.usdt:.2f}U{RST}"
    if executor:
        risk = executor.risk_status()
        if risk:
            extra += f" | {risk}"
        # PR0: conf 分桶展示，仅显示有样本的档位
        cs = executor.conf_stats
        bucket_parts = []
        for k in ('高', '中', '低'):
            b = cs.get(k, {'w': 0, 'l': 0})
            t = b['w'] + b['l']
            if t > 0:
                bucket_parts.append(f"{k}{b['w']}/{t}")
        if bucket_parts:
            extra += f" | {' '.join(bucket_parts)}"
    print(f"[{ts}] {SYMBOL.upper()} {price:.1f} | {rng} | 信号: {n_sig}{extra}", flush=True)

def log_signal(sig: Signal):
    try:
        p = Path(__file__).resolve().parent.parent.parent / LOG_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.fromtimestamp(sig.ts).isoformat()
        with open(p, 'a') as f:
            f.write(f"{ts} | {sig.direction} | px={sig.price:.2f} | "
                    f"rng={sig.range_low:.1f}-{sig.range_high:.1f} | "
                    f"wick={sig.wick_pct*100:.2f}% | "
                    f"conf={sig.confidence}\n")
    except Exception:
        pass

# PR0: 决策日志——每个 wick 候选写一行 JSONL，含 reject_reason，
# 给后续过滤器调参提供归因数据。wick_pos_pct 在 PR1 引入，PR0 阶段填 None。
def log_decision(ts: float, direction: str, price: float,
                 r: RangeStatus, w, conf: str, decided: bool,
                 reject_reason: str = ''):
    try:
        p = Path(__file__).resolve().parent.parent.parent / "logs" / "event_bot_decisions.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": datetime.fromtimestamp(ts).isoformat(),
            "symbol": SYMBOL.upper(),
            "direction": direction,
            "price": round(price, 2),
            "range_low": round(r.low, 2),
            "range_high": round(r.high, 2),
            "range_width": round(r.width_pct, 6),
            "wick_breach": round(w.breach_pct, 6) if w else None,
            "wick_pos_pct": getattr(w, 'pos_pct', None) if w else None,
            "conf": conf,
            "decided": decided,
            "reject_reason": reject_reason,
        }
        with open(p, 'a') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════
# 下单 + 结算跟踪
# ═══════════════════════════════════════════════════════════

@dataclass
class TrackedOrder:
    side: str
    entry_price: float
    settle_at: float
    amount: float
    event_id: str
    range_width: float = 0.0
    wick_breach: float = 0.0
    wick_revert: float = 0.0
    volume_ratio: float = 0.0
    momentum_slope: float = 0.0
    hour: int = 0
    confidence: str = ""
    won: bool = False

class OrderExecutor:
    def __init__(self):
        self._order_times: deque[float] = deque()
        self._pending: list[TrackedOrder] = []     # 未结算
        self._settled: list[TrackedOrder] = []     # 已结算（最近50条）
        self.wins = 0
        self.losses = 0
        self.profit = 0.0
        self.consec_loss = 0        # 当前连跪数
        self.max_consec_loss = 0    # 历史最大连跪
        self.paused_until = 0.0     # 风控暂停到何时（自动到期）
        self.manual_paused = False  # TG /pause 手动暂停（只能 /resume 解）
        self.daily_loss = 0.0       # 当日亏损
        self._daily_date = ""       # 当日日期
        # PR0: 按 confidence 分桶记胜率，给后续过滤器调参提供依据
        self.conf_stats: dict = {'高': {'w': 0, 'l': 0},
                                 '中': {'w': 0, 'l': 0},
                                 '低': {'w': 0, 'l': 0}}

    def can_order(self) -> bool:
        if not BINANCEELF_TOKEN:
            return False
        if self.manual_paused:
            return False
        now = time.time()

        # 连跪暂停
        if now < self.paused_until:
            return False

        # 当日亏损上限
        today = datetime.now().strftime('%Y%m%d')
        if today != self._daily_date:
            self.daily_loss = 0.0
            self._daily_date = today
        if self.daily_loss <= -RISK_DAILY_LOSS_CAP:
            return False

        if not AUTO_TRADE:
            # 模拟模式也遵守风控，但不限次数
            while self._order_times and self._order_times[0] < now - 3600:
                self._order_times.popleft()
            return len(self._order_times) < RISK_MAX_PER_HOUR

        while self._order_times and self._order_times[0] < now - 3600:
            self._order_times.popleft()
        return len(self._order_times) < RISK_MAX_PER_HOUR

    def reflect(self) -> str:
        """对比最近赢/输单的上下文，找出差异模式"""
        recent = self._settled[-30:]
        wins = [o for o in recent if o.won]
        losses = [o for o in recent if not o.won]
        if len(wins) < 3 or len(losses) < 2:
            return ""

        def avg(items, attr):
            vals = [getattr(o, attr, 0) for o in items if getattr(o, attr, 0) > 0]
            return sum(vals) / len(vals) if vals else 0

        findings = []
        # 对比区间宽度
        ww = avg(wins, 'range_width')
        lw = avg(losses, 'range_width')
        if lw > ww * 1.3:
            findings.append(f"输单区间偏宽 ({lw*100:.2f}% vs {ww*100:.2f}%) → 收紧 RANGE_MAX_WIDTH")

        # 对比针幅
        wb = avg(wins, 'wick_breach')
        lb = avg(losses, 'wick_breach')
        if lb < wb * 0.7:
            findings.append(f"输单针幅偏小 ({lb*100:.2f}% vs {wb*100:.2f}%) → 提高 WICK_BREACH_RATIO")

        # 对比动量
        wm = avg(wins, 'momentum_slope')
        lm = avg(losses, 'momentum_slope')
        if lm > wm * 1.3:
            findings.append(f"输单动量大 ({lm*100:.3f}% vs {wm*100:.3f}%) → 收紧 MOMENTUM_MAX_SLOPE")

        # 对比时段
        loss_hours = [o.hour for o in losses]
        from collections import Counter
        hour_cnt = Counter(loss_hours)
        worst_hour = hour_cnt.most_common(1)[0]
        if worst_hour[1] >= 2:
            findings.append(f"输单集中在 {worst_hour[0]}:00 附近 → 该时段加过滤")

        if not findings:
            findings.append("未发现显著模式差异，可能为随机波动")
        return "\n".join(f"  • {f}" for f in findings)

    def risk_status(self) -> str:
        """返回风控状态文本"""
        parts = []
        if self.manual_paused:
            parts.append(f"{YELLOW}⏸手动{RST}")
        if self.consec_loss >= 2:
            parts.append(f"{RED}连跪{self.consec_loss}{RST}")
        if time.time() < self.paused_until:
            remain = int(self.paused_until - time.time())
            parts.append(f"{RED}暂停{remain//60}分{RST}")
        if self.daily_loss <= -RISK_DAILY_LOSS_CAP:
            parts.append(f"{RED}日亏达上限{RST}")
        return " ".join(parts) if parts else ""

    def execute(self, sig: Signal, price: float,
                ctx: dict = None) -> bool:
        """下单。AUTO_TRADE=False 时模拟。ctx 为决策上下文。"""
        if not self.can_order():
            return False

        side = 'Long' if sig.direction == 'CALL' else 'Short'

        if AUTO_TRADE:
            payload = {
                "token": BINANCEELF_TOKEN,
                "symbol": SYMBOL.upper(),
                "side": side,
                "timeType": TIME_TYPE,
                "amount": AMOUNT
            }
            try:
                req = urllib.request.Request(
                    BINANCEELF_URL,
                    data=json.dumps(payload).encode(),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = resp.read().decode()
                    status = resp.status
            except Exception as e:
                print(f"  {RED}[!] 下单失败: {e}{RST}")
                return False

            if status != 200:
                print(f"  {RED}[!] 下单返回 {status}: {body}{RST}")
                return False
            try:
                resp_json = json.loads(body)
                if resp_json.get('code') not in (0, '0', None) or resp_json.get('success') is False:
                    print(f"  {RED}[!] 下单业务失败: {body}{RST}")
                    return False
            except json.JSONDecodeError:
                pass

            self._order_times.append(time.time())
            print(f"  {GREEN}[✓] 已下单 {side} {AMOUNT}U  "
                  f"{SYMBOL.upper()} {CONTRACT_DURATION}min  入场价 {price:.1f}{RST}")
        else:
            self._order_times.append(time.time())
            print(f"  {YELLOW}[◎] 模拟 {side} {AMOUNT}U  "
                  f"{SYMBOL.upper()} {CONTRACT_DURATION}min  入场价 {price:.1f}{RST}")

        ctx = ctx or {}
        order = TrackedOrder(
            side=side,
            entry_price=price,
            settle_at=time.time() + CONTRACT_DURATION * 60 + 30,
            amount=AMOUNT,
            event_id="sim" if not AUTO_TRADE else "",
            range_width=ctx.get('range_width', 0),
            wick_breach=ctx.get('wick_breach', 0),
            wick_revert=ctx.get('wick_revert', 0),
            volume_ratio=ctx.get('volume_ratio', 0),
            momentum_slope=ctx.get('momentum_slope', 0),
            hour=ctx.get('hour', 0),
            confidence=ctx.get('confidence', ''),
        )
        self._pending.append(order)
        return True

    def settle(self, current_price: float):
        """检查到期订单，用当前价格判定输赢"""
        now = time.time()
        to_settle = [o for o in self._pending if now >= o.settle_at]
        for o in to_settle:
            self._pending.remove(o)
            if o.side == 'Long':
                won = current_price > o.entry_price
            else:
                won = current_price < o.entry_price

            if won:
                self.wins += 1
                self.consec_loss = 0
                pnl = o.amount * 0.85
                self.profit += pnl
                self.daily_loss += pnl
                o.won = True
                self.conf_stats.setdefault(o.confidence, {'w': 0, 'l': 0})['w'] += 1
                print(f"\n  {GREEN}[✓] 结算赢  {o.side}  "
                      f"入场{o.entry_price:.1f} → 现价{current_price:.1f}  "
                      f"+{pnl:.2f}U{RST}")
                tg_settle = f"{'📈' if o.side=='Long' else '📉'} <b>结算赢</b>  {o.side}  "
            else:
                self.losses += 1
                self.consec_loss += 1
                if self.consec_loss > self.max_consec_loss:
                    self.max_consec_loss = self.consec_loss
                pnl = -o.amount
                self.profit += pnl
                self.daily_loss += pnl
                self.conf_stats.setdefault(o.confidence, {'w': 0, 'l': 0})['l'] += 1
                print(f"\n  {RED}[✗] 结算输  {o.side}  "
                      f"入场{o.entry_price:.1f} → 现价{current_price:.1f}  "
                      f"{pnl:.2f}U{RST}")
                tg_settle = f"{'📈' if o.side=='Long' else '📉'} <b>结算输</b>  {o.side}  "

                # 3 连跪：反思分析
                if self.consec_loss == RISK_REFLECT_CONSEC:
                    analysis = self.reflect()
                    if analysis:
                        msg = (f"🔍 <b>连跪{RISK_REFLECT_CONSEC}反思</b>\n{analysis}\n"
                               f"总{self.wins}W/{self.losses}L "
                               f"({self.win_rate*100:.0f}%)")
                        print(f"\n  {YELLOW}{msg}{RST}")
                        tg_send(msg)

                # 5 连跪：暂停
                if self.consec_loss >= RISK_MAX_CONSEC_LOSS:
                    self.paused_until = time.time() + RISK_LOSS_PAUSE_MIN * 60
                    pause_msg = (f"⛔ 连跪{RISK_MAX_CONSEC_LOSS}次，"
                                 f"暂停{RISK_LOSS_PAUSE_MIN}分钟")
                    print(f"\n  {RED}{pause_msg}{RST}")
                    tg_send(f"🛑 <b>{pause_msg}</b>\n"
                            f"总{self.wins}W/{self.losses}L "
                            f"({self.win_rate*100:.0f}%) {self.profit:+.1f}U")

                # 日亏上限
                if self.daily_loss <= -RISK_DAILY_LOSS_CAP:
                    stop_msg = f"⛔ 当日亏损达{RISK_DAILY_LOSS_CAP}U，今日停单"
                    print(f"\n  {RED}{stop_msg}{RST}")
                    tg_send(f"🛑 <b>{stop_msg}</b>\n"
                            f"总{self.wins}W/{self.losses}L {self.profit:+.1f}U")

            self._settled.append(o)
            if len(self._settled) > 50:
                self._settled.pop(0)

            tg_settle += (f"入场{o.entry_price:.1f} → 现价{current_price:.1f}  "
                          f"{pnl:+.2f}U | "
                          f"总{self.wins}W/{self.losses}L "
                          f"({self.win_rate*100:.0f}%) "
                          f"{self.profit:+.1f}U")
            if self.consec_loss >= 2:
                tg_settle += f" 连跪{self.consec_loss}"
            if not AUTO_TRADE:
                tg_settle += " (模拟)"
            tg_send(tg_settle)

    @property
    def total(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.wins / self.total

    @property
    def pending_count(self) -> int:
        return len(self._pending)

# ═══════════════════════════════════════════════════════════
# 币安余额查询
# ═══════════════════════════════════════════════════════════

class BinanceBalance:
    def __init__(self):
        self.usdt = 0.0
        self._last_fetch = 0.0

    def fetch(self) -> float:
        """获取现货 USDT 余额，60 秒缓存"""
        now = time.time()
        if now - self._last_fetch < 60:
            return self.usdt

        if not BINANCE_API_KEY or not BINANCE_API_SECRET:
            return 0.0

        try:
            ts = int(time.time() * 1000)
            params = f"timestamp={ts}&recvWindow=10000"
            sig = hmac.new(
                BINANCE_API_SECRET.encode(), params.encode(), hashlib.sha256
            ).hexdigest()
            url = f"https://api.binance.com/api/v3/account?{params}&signature={sig}"

            req = urllib.request.Request(url)
            req.add_header("X-MBX-APIKEY", BINANCE_API_KEY)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            for b in data.get("balances", []):
                if b["asset"] == "USDT":
                    self.usdt = float(b["free"])
                    self._last_fetch = now
                    return self.usdt
        except Exception as e:
            print(f"  [!] 余额查询失败: {e}")
        return self.usdt

# ═══════════════════════════════════════════════════════════
# Telegram 通知
# ═══════════════════════════════════════════════════════════

def tg_send(text: str) -> bool:
    """发送消息到 TG 群，失败打印到 stdout 但不抛；重试 1 次"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }).encode()
    last_err = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, data=body,
                headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read()).get('ok', False)
        except Exception as e:
            last_err = e
            if attempt == 1:
                time.sleep(3)
    snippet = text.replace('\n', ' ')[:40]
    print(f"  [!] TG发送失败({type(last_err).__name__}): {snippet}...")
    return False

def fmt_tg_signal(sig: Signal) -> str:
    """生成发送到 TG 的信号文案"""
    emoji = "📈" if sig.direction == 'CALL' else "📉"
    side_cn = "做多" if sig.direction == 'CALL' else "做空"
    wick_cn = "下影" if sig.direction == 'CALL' else "上影"
    conf_stars = {'高': '⭐⭐⭐', '中': '⭐⭐', '低': '⭐'}
    msg = (
        f"{emoji} <b>接针信号 - {side_cn}</b>\n"
        f"品种: <code>{SYMBOL.upper()}</code> | {CONTRACT_DURATION}分钟\n"
        f"触发价: <code>{sig.price:.1f}</code>\n"
        f"区间: {sig.range_low:.1f} - {sig.range_high:.1f}"
        f" (宽{(sig.range_high/sig.range_low-1)*100:.2f}%)\n"
        f"{wick_cn}穿透: {sig.wick_pct*100:.2f}%\n"
        f"置信度: {conf_stars.get(sig.confidence, '⭐')}"
    )
    if not AUTO_TRADE:
        msg += "\n\n<i>模拟信号</i>"
    return msg

# ═══════════════════════════════════════════════════════════
# TG 命令监听
# ═══════════════════════════════════════════════════════════

class TgListener:
    """轮询 TG 消息，响应远程运维命令。

    白名单：只接受来自 TG_CHAT_ID 的消息；其他 chat_id 的消息**完全不回复**
    （不暴露 bot 在线，避免 token 泄露后被外部探测）。

    命令：
      /status /stats           - 状态/战绩
      /pause /resume           - 手动暂停/恢复（独立于风控自动暂停）
      /restart                 - 进程退出，依赖 launchd KeepAlive 拉起
      /tail [N]                - 信号日志最近 N 行（默认 20，封顶 50）
    """

    def __init__(self, executor=None):
        self._offset = 0
        self._last_daily = ""   # 上次日终总结日期
        self._executor = executor

    async def run(self, get_state):
        """get_state() -> dict 返回当前状态"""
        if not TG_BOT_TOKEN:
            return
        # 启动时丢弃所有 pending 的 update。
        # 关键：/restart 命令会让进程退出，但那条 TG 消息还在服务器队列里，
        # 不丢弃的话新进程拉起 → 又拉到 /restart → 又退出 → 死循环。
        self._consume_pending()
        while True:
            await asyncio.sleep(3)
            try:
                updates = self._get_updates()
                for upd in updates:
                    if 'message' in upd:
                        self._handle(upd, get_state)
            except Exception as e:
                print(f"  [!] TG轮询错误: {e}")

    def _consume_pending(self):
        """启动时把 TG 服务器上所有 pending 的 update ack 掉，避免重启风暴。"""
        try:
            params = {"timeout": 0}
            qs = urllib.parse.urlencode(params)
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates?{qs}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            results = data.get("result", [])
            if not results:
                return
            self._offset = results[-1]["update_id"] + 1
            # 再调一次带 offset 的 getUpdates，让服务器 ack 掉这些 pending 消息
            params = {"timeout": 0, "offset": self._offset}
            qs = urllib.parse.urlencode(params)
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates?{qs}"
            req = urllib.request.Request(url)
            urllib.request.urlopen(req, timeout=8).read()
            print(f"[tg] 启动时跳过 {len(results)} 条 pending update（避免重启风暴）")
        except Exception as e:
            print(f"  [!] TG 启动 consume 失败: {e}（不影响运行）")

    def _get_updates(self) -> list:
        params = {"timeout": 2, "offset": self._offset}
        qs = urllib.parse.urlencode(params)
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates?{qs}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        if not data.get("ok"):
            return []
        results = data.get("result", [])
        if results:
            self._offset = results[-1]["update_id"] + 1
        return results

    def _handle(self, upd: dict, get_state):
        msg = upd.get("message", {})
        text = msg.get("text", "")
        if not text or not text.startswith("/"):
            return

        # 白名单：只接受来自配置的 TG_CHAT_ID 的命令
        chat_id = msg.get("chat", {}).get("id")
        if str(chat_id) != str(TG_CHAT_ID):
            return  # 静默丢弃，不回复也不报错

        parts = text.strip().split()
        cmd = parts[0].lower()
        args = parts[1:]
        reply = ""

        if cmd == "/status":
            reply = self._fmt_status(get_state())
        elif cmd == "/stats":
            reply = self._fmt_stats(get_state())
        elif cmd == "/pause":
            reply = self._pause()
        elif cmd == "/resume":
            reply = self._resume()
        elif cmd == "/tail":
            n = 20
            if args:
                try:
                    n = max(1, min(50, int(args[0])))
                except ValueError:
                    pass
            reply = self._tail(n)
        elif cmd == "/restart":
            tg_send("🔄 <b>重启中...</b> (launchd 会自动拉起新进程)")
            print(f"\n  {YELLOW}[/restart] 收到 TG 命令，进程退出{RST}")
            os._exit(0)
        elif cmd == "/pull":
            self._pull()  # 成功会自己 os._exit(0)；失败/无更新会回复
            return
        else:
            return

        if reply:
            tg_send(reply)

    def _pause(self) -> str:
        if not self._executor:
            return "⚠ executor 未注入"
        if self._executor.manual_paused:
            return "已是暂停状态"
        self._executor.manual_paused = True
        return ("⏸ <b>已手动暂停</b>\n"
                "已下单 pending 继续走完结算；新信号不下单。\n"
                "用 /resume 恢复。")

    def _resume(self) -> str:
        if not self._executor:
            return "⚠ executor 未注入"
        if not self._executor.manual_paused:
            return "未在手动暂停状态"
        self._executor.manual_paused = False
        return "▶ <b>已恢复</b>，新信号正常下单"

    def _tail(self, n: int) -> str:
        from collections import deque
        log_path = Path(__file__).resolve().parent.parent.parent / LOG_FILE
        if not log_path.exists():
            return "无日志文件"
        try:
            with open(log_path) as f:
                lines = deque(f, maxlen=n)
        except Exception as e:
            return f"读日志失败: {e}"
        if not lines:
            return "日志为空"
        body = "".join(lines).rstrip()
        # TG 单条消息封顶 4096 字节，按需截断
        if len(body) > 3800:
            body = body[-3800:]
            body = "...(已截断)\n" + body
        return f"<b>最近 {len(lines)} 条信号</b>\n<pre>{body}</pre>"

    def _pull(self):
        """git pull 拿最新代码 + 自动重启。

        成功且有更新 → 回 ack 后 os._exit(0) 让 launchd 拉起新进程
        成功但无更新 → 回「已是最新」
        失败 → 回 stderr 摘要不重启
        """
        import subprocess
        repo = Path(__file__).resolve().parent.parent.parent
        try:
            r = subprocess.run(
                ['git', '-C', str(repo), 'pull', '--rebase', '--ff-only', 'origin', 'main'],
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            tg_send("⚠ <b>/pull 超时</b> (30s)，未重启")
            return
        except Exception as e:
            tg_send(f"⚠ <b>/pull 异常</b>: {e}")
            return

        out = ((r.stdout or '') + (r.stderr or '')).strip()
        if r.returncode != 0:
            snippet = out[-1500:] if len(out) > 1500 else out
            tg_send(f"⚠ <b>/pull 失败</b> (code {r.returncode})\n<pre>{snippet}</pre>")
            return

        if 'Already up to date' in out or 'is up to date' in out or not out:
            tg_send("✓ <b>已是最新</b>，无需重启")
            return

        # 拉到新提交：回 ack 后退出，由 launchd 拉起
        snippet = out[-1500:] if len(out) > 1500 else out
        tg_send(f"✓ <b>git pull 成功</b>\n<pre>{snippet}</pre>\n\n🔄 重启读新代码...")
        print(f"\n  {GREEN}[/pull] 拉到新提交，进程退出{RST}")
        os._exit(0)

    def _fmt_status(self, s: dict) -> str:
        ex = s.get('executor', {})
        rng = s.get('range', '')
        trading = "🟢" if s.get('trading_hours', True) else "🔴"
        lines = [
            f"<b>Bot 状态</b> {trading}",
            f"BTC: <code>{s.get('price', 0):.1f}</code>",
            f"区间: {rng}",
            f"信号: {s.get('signals', 0)}",
        ]
        if ex:
            if ex.get('manual_paused'):
                lines.append("⏸ <b>手动暂停中</b> (/resume 恢复)")
            t = ex.get('total', 0)
            if t > 0:
                lines.append(
                    f"战绩: {ex.get('wins',0)}W/{ex.get('losses',0)}L "
                    f"({ex.get('win_rate',0)*100:.0f}%) {ex.get('profit',0):+.1f}U"
                )
            cons = ex.get('consec_loss', 0)
            if cons >= 2:
                lines.append(f"⚠ 连跪: {cons}")
        if s.get('auto_trade'):
            lines.append("模式: 实盘")
        else:
            lines.append("模式: 模拟")
        return "\n".join(lines)

    def _fmt_stats(self, s: dict) -> str:
        ex = s.get('executor', {})
        t = ex.get('total', 0)
        if t == 0:
            return "暂无交易记录"
        return "\n".join([
            f"<b>交易统计</b>",
            f"总笔数: {t}",
            f"胜: {ex.get('wins',0)}  负: {ex.get('losses',0)}",
            f"胜率: {ex.get('win_rate',0)*100:.1f}%",
            f"累计盈亏: {ex.get('profit',0):+.2f}U",
            f"最大连跪: {ex.get('max_consec',0)}",
        ])

# ═══════════════════════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════════════════════

def acquire_single_instance_lock():
    """flock 独占 logs/event_bot.pid,已有实例运行时直接退出"""
    pid_path = Path(__file__).resolve().parent.parent.parent / "logs" / "event_bot.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(pid_path, "a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.seek(0)
        existing = f.read().strip() or "?"
        print(f"[!] 已有 bot 实例运行 (pid={existing}),退出")
        f.close()
        sys.exit(1)
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f  # 进程退出时 fd 关闭,锁自动释放


async def main():
    print(f"{BOLD}震荡区间接针 Bot{RST}")
    print(f"品种: {SYMBOL.upper()}  |  区间最大宽度: {RANGE_MAX_WIDTH*100}%  |  "
          f"针阈值: 区间宽×{WICK_BREACH_RATIO}  |  量阈值: ×{VOLUME_MIN_RATIO}  |  "
          f"动量上限: {MOMENTUM_MAX_SLOPE}")
    print(f"冷却: {SIGNAL_COOLDOWN}s  |  目标合约: {CONTRACT_DURATION}min  |  "
          f"置信门槛: {MIN_CONFIDENCE}  |  信号日志: {LOG_FILE}")
    if SIGNAL_COOLDOWN < 60:
        print(f"{YELLOW}[!] SIGNAL_COOLDOWN={SIGNAL_COOLDOWN} 偏低，建议 ≥ 300 "
              f"抑制簇集（同区间多根连续扫针 + 重连回放都会产生重复信号）{RST}")
    if _LEGACY_IN_CONFIG:
        print(f"{YELLOW}[!] config.py 里有 {len(_LEGACY_IN_CONFIG)} 个策略字段已迁移到 "
              f"params.py（进 git）：{', '.join(_LEGACY_IN_CONFIG)}\n"
              f"    当前 params.py 的值已覆盖这些 config 字段，但 config 里残留会让人困惑。\n"
              f"    建议从 config.py 删掉这些行（只保留 token / API key / PROXY / AUTO_TRADE）。{RST}")
    if AUTO_TRADE:
        print(f"{GREEN}自动下单: 已启用 (每单{AMOUNT}U, 限{RISK_MAX_PER_HOUR}次/时){RST}")
    else:
        print(f"{YELLOW}自动下单: 关闭 (仅发信号){RST}")
    if PROXY:
        print(f"代理: {PROXY}")
    print()

    # 连通性
    rdet = RangeDetector(lookback=RANGE_LOOKBACK, max_width=RANGE_MAX_WIDTH)
    wdet = WickDetector(breach_ratio=WICK_BREACH_RATIO)
    eng = SignalEngine()
    executor = OrderExecutor()
    balance = BinanceBalance()
    stream = BinanceStream()
    if not stream.test_connectivity():
        print("[!] 网络不通，退出")
        return
    price = 0.0
    sig_count = 0
    pending_entry = None  # (sig, ctx, deadline_ts) — on_kline 触发后等下一次 on_1s 用其 close 做 entry

    def on_kline(c: Candle):
        nonlocal price, sig_count, pending_entry
        price = c.close
        rdet.add(c)

        r = rdet.analyze()
        if not (r.consolidating and is_trading_hours(only_off_hours=TRADE_ONLY_OFF_HOURS,
                                                     block_start=TRADE_END_HOUR,
                                                     block_end=TRADE_START_HOUR)):
            return
        if not momentum_ok(rdet, MOMENTUM_MAX_SLOPE):
            return
        w = wdet.detect(c, r)
        if not w:
            return
        # 到这里说明区间内出现 wick 候选，无论结果如何都会写一条 decision 日志
        direction_pre = 'CALL' if w.direction == 'down' else 'PUT'

        # 量能过滤：真扫盘性穿针通常伴随放量；无量穿针多为趋势启动早期
        if not volume_ok(c, list(rdet.buf)[:-1], VOLUME_MIN_RATIO):
            log_decision(time.time(), direction_pre, c.close, r, w,
                         conf='', decided=False, reject_reason='volume_low')
            return

        sig = eng.process(r, w, c.close)
        if not sig:
            log_decision(time.time(), direction_pre, c.close, r, w,
                         conf='', decided=False, reject_reason='cooldown')
            return

        sig_count += 1
        fmt_signal(sig)
        log_signal(sig)
        tg_send(fmt_tg_signal(sig))

        # 置信度过滤：低于 MIN_CONFIDENCE 的信号显示但不下单
        if _CONF_RANK.get(sig.confidence, 0) < _CONF_RANK.get(MIN_CONFIDENCE, 1):
            print(f"  {YELLOW}[skip] 置信 {sig.confidence} < {MIN_CONFIDENCE}，不下单{RST}")
            log_decision(sig.ts, sig.direction, sig.price, r, w,
                         conf=sig.confidence, decided=False, reject_reason='low_confidence')
            return

        # 构建决策上下文
        slp = momentum_slope(rdet)
        items = list(rdet.buf)
        avg_vol = sum(x.vol for x in items) / len(items) if items else 0
        ctx = {
            'range_width': r.width_pct,
            'wick_breach': w.breach_pct,
            'wick_revert': 0,
            'volume_ratio': (c.vol / avg_vol) if avg_vol > 0 else 0,
            'momentum_slope': abs(slp) if slp else 0,
            'hour': datetime.now().hour,
            'confidence': sig.confidence,
        }
        # 推迟到下一个 1s 推送下单：entry = 触发后下一秒 close ≈ Binance 指数价
        # 5s 内未消费就丢弃。带 r/w 是为了在 on_1s 写决策日志时能拿到上下文
        pending_entry = (sig, ctx, r, w, time.time() + 5)

    def on_1s(c: Candle):
        nonlocal price, pending_entry
        price = c.close
        executor.settle(price)

        if pending_entry is not None:
            sig, ctx, r_pe, w_pe, deadline = pending_entry
            if time.time() > deadline:
                print(f"  {YELLOW}[!] pending_entry 超时 5s 丢弃: {sig.direction}{RST}")
                log_decision(sig.ts, sig.direction, sig.price, r_pe, w_pe,
                             conf=sig.confidence, decided=False,
                             reject_reason='pending_timeout')
                pending_entry = None
            else:
                pending_entry = None
                ok = executor.execute(sig, c.close, ctx)
                log_decision(time.time(), sig.direction, c.close, r_pe, w_pe,
                             conf=sig.confidence, decided=bool(ok),
                             reject_reason='' if ok else 'risk_block')

    ws_seen_connected = False
    def on_status(s: str):
        nonlocal ws_seen_connected
        print(f"[ws] {s}")
        if s == "connected":
            if ws_seen_connected:
                # 重连：只补 RangeDetector buf，不重放 on_kline。
                # 回放历史 K 线触发新信号是 bug —— 那些机会已经过去，重新下单只会
                # 在重连瞬间制造高度相关的簇集。信号检测从下一根新 K 线起。
                hist = stream.fetch_history()
                if hist:
                    rdet.buf.clear()
                    for c in hist:
                        rdet.add(c)
                    print(f"[ws] 重连后补 {len(hist)} 根 {KLINE_INTERVAL} K线 "
                          f"(buf 就绪，信号检测从下一根新 K 线起)")
            ws_seen_connected = True

    stream.on_kline = on_kline
    stream.on_1s = on_1s
    stream.on_status = on_status

    # 加载历史
    print("加载历史 K线...")
    hist = stream.fetch_history()
    for c in hist:
        rdet.add(c)
    print(f"已加载 {len(hist)} 根 {KLINE_INTERVAL} K线, 区间检测就绪\n")

    async def status_loop():
        last_daily = ""
        while True:
            await asyncio.sleep(8)
            balance.fetch()
            fmt_status(price, rdet.analyze(), sig_count, executor, balance)

            # 每天 00:00 发日终总结
            today = datetime.now().strftime('%Y%m%d')
            if today != last_daily and executor.total > 0:
                now = datetime.now()
                if now.hour == 0 and now.minute < 5:
                    last_daily = today
                    summary = (
                        f"📊 <b>日终总结 {now.strftime('%m/%d')}</b>\n"
                        f"信号: {sig_count} | "
                        f"交易: {executor.wins}W/{executor.losses}L "
                        f"({executor.win_rate*100:.0f}%)\n"
                        f"盈亏: {executor.profit:+.1f}U | "
                        f"最大连跪: {executor.max_consec_loss}\n"
                        f"余额: {balance.usdt:.2f}U"
                    )
                    if not AUTO_TRADE:
                        summary += " (模拟)"
                    tg_send(summary)

    # TG 命令监听
    tgl = TgListener(executor=executor)
    def get_state():
        r = rdet.analyze()
        return {
            'price': price,
            'range': f"{r.low:.1f}-{r.high:.1f} ({r.width_pct*100:.2f}%)" if r.consolidating else "非震荡",
            'trading_hours': is_trading_hours(),
            'signals': sig_count,
            'auto_trade': AUTO_TRADE,
            'executor': {
                'total': executor.total,
                'wins': executor.wins,
                'losses': executor.losses,
                'win_rate': executor.win_rate,
                'profit': executor.profit,
                'consec_loss': executor.consec_loss,
                'max_consec': executor.max_consec_loss,
                'pending': executor.pending_count,
                'manual_paused': executor.manual_paused,
            }
        }
    tg_task = asyncio.create_task(tgl.run(get_state))
    st = asyncio.create_task(status_loop())

    try:
        await stream.start()
    except KeyboardInterrupt:
        print(f"\n\n停止。本次发出 {sig_count} 个信号")
    finally:
        tg_task.cancel()
        st.cancel()
        await stream.stop()

if __name__ == '__main__':
    _lock = acquire_single_instance_lock()
    asyncio.run(main())
