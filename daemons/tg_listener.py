"""
Telegram 成功群监听守护进程。

监听 TG_SUCCESS_CHAT_ID，每条消息（含截图）落盘到
state/incoming/pnr_{ts_ms}_{msg_id}.json。

用法：
  python3 daemons/tg_listener.py
"""

import json
import os
import sys
from datetime import timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from loguru import logger

load_dotenv(_ROOT / ".env")

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

_INCOMING_DIR    = _ROOT / "state" / "incoming"
_ATTACHMENTS_DIR = _ROOT / "state" / "attachments"
_TZ_CST = timezone(timedelta(hours=8))

_SUCCESS_CHAT_ID = int(os.environ["TG_SUCCESS_CHAT_ID"])


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg:
        return

    ts     = msg.date.astimezone(_TZ_CST)
    ts_ms  = int(msg.date.timestamp() * 1000)
    msg_id = msg.message_id
    text   = msg.text or msg.caption or ""
    sender = msg.from_user

    attachments: list[str] = []
    if msg.photo:
        _ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        photo_size = msg.photo[-1]
        tg_file    = await photo_size.get_file()
        att_path   = _ATTACHMENTS_DIR / f"pnr_{ts_ms}_{msg_id}_0.jpg"
        await tg_file.download_to_drive(str(att_path))
        attachments.append(str(att_path))

    event = {
        "type":        "pnr",
        "ts":          ts.isoformat(timespec="seconds"),
        "ts_ms":       ts_ms,
        "msg_id":      msg_id,
        "from_uid":    str(sender.id) if sender else "",
        "from_name":   sender.full_name if sender else "",
        "text":        text,
        "attachments": attachments,
        "processed":   False,
    }

    _INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    out = _INCOMING_DIR / f"pnr_{ts_ms}_{msg_id}.json"
    out.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"PNR 事件落盘：{out.name}  文本：{text[:60]}")


def main() -> None:
    token = os.environ["TG_BOT_TOKEN"]
    proxy = os.getenv("HTTP_PROXY", "")

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )

    builder = ApplicationBuilder().token(token)
    if proxy:
        builder = builder.proxy(proxy)
    app = builder.build()

    app.add_handler(
        MessageHandler(
            filters.Chat(chat_id=_SUCCESS_CHAT_ID) & (filters.TEXT | filters.PHOTO),
            _on_message,
        )
    )

    logger.info(f"监听 TG 成功群 chat_id={_SUCCESS_CHAT_ID}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
