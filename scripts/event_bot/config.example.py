"""震荡区间接针策略 - 配置模板

复制为 config.py 后填入实际 token 才能跑：
    cp config.example.py config.py
config.py 已被 .gitignore，不会进仓库。
"""

# ------- 网络 -------
PROXY = "http://127.0.0.1:7897"  # 代理地址（不需要走代理可设 ""）

# ------- 币安 API（只读，查余额） -------
BINANCE_API_KEY = ""
BINANCE_API_SECRET = ""

# ------- 行情 -------
SYMBOL = "btcusdt"            # 交易对

# ------- 震荡区间检测（1m K 线维度） -------
# 参数来自 walkforward.py 验证：14 天前 7 调参 + 后 7 验证胜率 68%
RANGE_LOOKBACK = 40            # 用过去 N 根 1m 蜡烛判断区间
RANGE_MAX_WIDTH = 0.0080       # 区间最大宽度（10/90 分位）

# ------- 接针检测（1m 单根蜡烛形态学：穿透 + 收盘回到区间内） -------
WICK_MIN_BREACH = 0.0005       # low/high 穿透区间边界的最小幅度
MOMENTUM_MAX_SLOPE = 0.0002    # 区间内价格趋势斜率上限（超过=强趋势，不接）

# ------- 信号 -------
SIGNAL_COOLDOWN = 60
CONTRACT_DURATION = 10

# ------- 交易时段（北京时间，基于美股真实交易日历） -------
TRADE_ONLY_OFF_HOURS = True      # 避开美股时段（周末+节假日自动跳过）
TRADE_START_HOUR = 4             # 04:00 恢复交易
TRADE_END_HOUR = 20              # 20:00 暂停交易（美股盘前开始）

# ------- 自动下单（binanceelf 发单平台） -------
AUTO_TRADE = False               # 是否自动下单（先 False 看信号效果）
BINANCEELF_TOKEN = ""            # 发单平台 token
BINANCEELF_URL = "https://binanceelf.com/bg/event/hook"
AMOUNT = 5                       # 每单金额 (USDT)
RISK_MAX_PER_HOUR = 4            # 每小时最多下单次数
RISK_MAX_CONSEC_LOSS = 5         # 连跪上限（5连=0.17%概率，真异常）
RISK_REFLECT_CONSEC = 3          # 连跪反思阈值（只分析不停）
RISK_LOSS_PAUSE_MIN = 120        # 连跪暂停分钟数
RISK_DAILY_LOSS_CAP = 25         # 当日亏损上限 (USDT)

# timeType 映射: 合约时长(分钟) -> timeType
TIME_TYPE_MAP = {5: 2, 10: 0, 15: 3, 30: 1, 60: 5, 1440: 10}
TIME_TYPE = TIME_TYPE_MAP.get(CONTRACT_DURATION, 3)

# ------- Telegram 通知 -------
TG_BOT_TOKEN = ""
TG_CHAT_ID = ""

# ------- 输出 -------
LOG_FILE = "logs/event_bot_signals.log"
