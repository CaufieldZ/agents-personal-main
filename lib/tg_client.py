"""
Telegram Bot 发消息封装（文字 + 图片）。

从 .env 读取 TG_BOT_TOKEN 和 HTTP_PROXY。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def _token() -> str:
    return os.environ["TG_BOT_TOKEN"]


def _proxies() -> dict | None:
    proxy = os.getenv("HTTP_PROXY", "")
    return {"http": proxy, "https": proxy} if proxy else None


def send_text(chat_id: str, text: str) -> None:
    import requests

    resp = requests.post(
        f"https://api.telegram.org/bot{_token()}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        proxies=_proxies(),
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram 返回错误：{result}")


def send_photo(chat_id: str, photo_path: str | Path, caption: str = "") -> None:
    import requests

    with open(photo_path, "rb") as f:
        resp = requests.post(
            f"https://api.telegram.org/bot{_token()}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": f},
            proxies=_proxies(),
            timeout=30,
        )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram 返回错误：{result}")
