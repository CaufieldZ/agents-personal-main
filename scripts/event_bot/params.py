"""event_bot 策略 / 风控 / 时段参数（进 git，跨机同步）。

token、API key、代理走 config.py（gitignored）。
bot.py 加载顺序：from config import * → from params import *
所以 params 里的字段会覆盖 config 里同名的字段。

修改这里的参数后流程：
    git commit + push  →  TG 发 /pull  →  家里 bot 自动 pull + restart
不用 ssh、不用 vim。
"""

# ───── 行情 ─────
SYMBOL = "btcusdt"
KLINE_INTERVAL = "5m"

# ───── 震荡区间检测（5m K 线维度） ─────
RANGE_LOOKBACK = 36            # 36 根 5m = 3 小时历史
RANGE_MAX_WIDTH = 0.006        # 区间最大宽度 0.6%（10/90 分位）

# ───── 接针检测（穿透 + 收盘回到区间内） ─────
WICK_MIN_BREACH = 0.0005
WICK_BREACH_RATIO = 0.05       # 穿透 ≥ 区间宽度 × ratio
VOLUME_MIN_RATIO = 0.0         # 量能过滤已关（回测无 edge）
MOMENTUM_MAX_SLOPE = 0.0002    # 区间内斜率上限

# ───── 信号 / 合约 ─────
SIGNAL_COOLDOWN = 300          # 5min 冷却，抑制簇集
MIN_CONFIDENCE = '中'          # 低于此置信度的信号不下单（仍 log + 推 TG）
CONTRACT_DURATION = 30         # 30min 合约 = 6 根 5m K 线

# ───── 交易时段（北京时间，基于美股真实交易日历） ─────
TRADE_ONLY_OFF_HOURS = True
TRADE_START_HOUR = 4           # 04:00 恢复
TRADE_END_HOUR = 20            # 20:00 暂停（美股盘前）

# ───── 下单 / 风控 ─────
AMOUNT = 5                     # 每单 USDT
RISK_MAX_PER_HOUR = 4
RISK_MAX_CONSEC_LOSS = 5       # 5连=0.17%概率，真异常
RISK_REFLECT_CONSEC = 3        # 连跪反思阈值（只分析）
RISK_LOSS_PAUSE_MIN = 120      # 连跪暂停分钟
RISK_DAILY_LOSS_CAP = 25       # 日亏上限 USDT

# ───── 平台 endpoint（公开） ─────
BINANCEELF_URL = "https://binanceelf.com/bg/event/hook"

# Binance 事件合约只支持 10/30/60/1440 min
TIME_TYPE_MAP = {10: 0, 30: 1, 60: 5, 1440: 10}
TIME_TYPE = TIME_TYPE_MAP[CONTRACT_DURATION]

# ───── 输出 ─────
LOG_FILE = "logs/event_bot_signals.log"
