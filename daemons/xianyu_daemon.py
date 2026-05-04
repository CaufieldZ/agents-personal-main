"""
闲鱼监听守护进程。

用法：
  python3 daemons/xianyu_daemon.py

Cookie 从 config/xianyu_cookies.txt 读取。
收到的私信/订单状态事件写入 state/incoming/chat_*.json。
"""

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "vendor" / "xianyu_live"))
sys.path.insert(0, str(_ROOT))

from loguru import logger
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from main import XianyuLive  # noqa: E402  (vendor/xianyu_live/main.py)

_COOKIES_PATH       = _ROOT / "config" / "xianyu_cookies.txt"
_COOKIE_DIRTY_FLAG  = _ROOT / "state" / "cookie_dirty.flag"


def main() -> None:
    if _COOKIE_DIRTY_FLAG.exists():
        logger.error(
            f"检测到 cookie_dirty flag：{_COOKIE_DIRTY_FLAG}\n"
            "上一次运行触发风控，需要人工过滑块。流程：\n"
            "  1. 浏览器登录闲鱼网页版，点消息触发滑块并通过\n"
            "  2. 复制完整 Cookie（含 x5sec）到 config/xianyu_cookies.txt\n"
            "  3. 删除 state/cookie_dirty.flag\n"
            "  4. 重新启动守护进程"
        )
        # 退出 0 让 launchd KeepAlive=SuccessfulExit:false 不再重启
        sys.exit(0)

    if not _COOKIES_PATH.exists():
        logger.error(f"Cookie 文件不存在：{_COOKIES_PATH}")
        sys.exit(1)

    cookies_str = _COOKIES_PATH.read_text(encoding="utf-8").strip()
    if not cookies_str:
        logger.error("Cookie 文件为空")
        sys.exit(1)

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )

    logger.info(f"启动闲鱼监听，Cookie 文件：{_COOKIES_PATH}")
    live = XianyuLive(cookies_str)
    asyncio.run(live.main())


if __name__ == "__main__":
    main()
