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

_COOKIES_PATH = _ROOT / "config" / "xianyu_cookies.txt"


def main() -> None:
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
