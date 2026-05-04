"""
轻量闲鱼发消息客户端。

每次调用 send_message 都开一个短连接：登录 → 注册 → 发消息 → 断开。
仅用于命令脚本（commands/reply.py 等），不是守护进程。
"""

import asyncio
import base64
import json
import os
import random
import sys
import time
from datetime import datetime, time as dtime, timezone, timedelta
from pathlib import Path

import websockets

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "vendor" / "xianyu_live"))  # XianyuApis 内部用裸 utils 导入

from vendor.xianyu_live.XianyuApis import XianyuApis
from vendor.xianyu_live.utils.xianyu_utils import (
    generate_device_id,
    generate_mid,
    generate_uuid,
    trans_cookies,
)

_COOKIES_PATH = _ROOT / "config" / "xianyu_cookies.txt"
_WS_URL = "wss://wss-goofish.dingtalk.com/"


def _read_cookies() -> str:
    txt = _COOKIES_PATH.read_text(encoding="utf-8").strip()
    return txt


def _build_text_payload(cid: str, to_uid: str, my_uid: str, text: str) -> str:
    content = {"contentType": 1, "text": {"text": text}}
    content_b64 = base64.b64encode(json.dumps(content).encode()).decode()
    msg = {
        "lwp": "/r/MessageSend/sendByReceiverScope",
        "headers": {"mid": generate_mid()},
        "body": [
            {
                "uuid": generate_uuid(),
                "cid": f"{cid}@goofish",
                "conversationType": 1,
                "content": {
                    "contentType": 101,
                    "custom": {"type": 1, "data": content_b64},
                },
                "redPointPolicy": 0,
                "extension": {"extJson": "{}"},
                "ctx": {"appVersion": "1.0", "platform": "web"},
                "mtags": {},
                "msgReadStatusSetting": 1,
            },
            {
                "actualReceivers": [
                    f"{to_uid}@goofish",
                    f"{my_uid}@goofish",
                ]
            },
        ],
    }
    return json.dumps(msg)


async def _send_once(chat_id: str, to_uid: str, text: str) -> None:
    cookies_str = _read_cookies()
    cookies = trans_cookies(cookies_str)
    my_uid = cookies["unb"]
    device_id = generate_device_id(my_uid)

    xianyu = XianyuApis()
    xianyu.session.cookies.update(cookies)
    token_result = xianyu.get_token(device_id)
    token = token_result["data"]["accessToken"]

    headers = {
        "Cookie": cookies_str,
        "Host": "wss-goofish.dingtalk.com",
        "Connection": "Upgrade",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://www.goofish.com",
    }

    async with websockets.connect(_WS_URL, extra_headers=headers) as ws:
        # 注册
        reg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": device_id,
                "mid": generate_mid(),
            },
        }
        await ws.send(json.dumps(reg))
        await asyncio.sleep(random.uniform(0.8, 1.6))

        # ackDiff
        ack_diff = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": "5701741704675979 0"},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": int(time.time() * 1000) * 1000,
                    "seq": 0,
                    "timestamp": int(time.time() * 1000),
                }
            ],
        }
        await ws.send(json.dumps(ack_diff))
        await asyncio.sleep(random.uniform(0.4, 0.9))

        # 发送消息
        payload = _build_text_payload(chat_id, to_uid, my_uid, text)
        await ws.send(payload)
        await asyncio.sleep(random.uniform(0.4, 0.9))


_TZ_CST = timezone(timedelta(hours=8))


def _parse_hhmm(s: str, default: dtime) -> dtime:
    try:
        h, m = s.split(":")
        return dtime(int(h), int(m))
    except Exception:
        return default


def _quiet_window() -> tuple[dtime, dtime]:
    start = _parse_hhmm(os.getenv("XIANYU_QUIET_START", "01:00"), dtime(1, 0))
    end   = _parse_hhmm(os.getenv("XIANYU_QUIET_END",   "07:30"), dtime(7, 30))
    return start, end


def _is_quiet_now() -> bool:
    now = datetime.now(_TZ_CST).time()
    start, end = _quiet_window()
    if start <= end:
        return start <= now < end
    # 跨午夜，例如 23:00 ~ 07:00
    return now >= start or now < end


class QuietHoursError(RuntimeError):
    pass


def _humanize_delay(text: str) -> float:
    """模拟人工：base 15-60s + 每字 0.05-0.2s，封顶 90s。

    比真人键盘慢——目标不是逐字模拟，是制造「看到消息走开一会儿才回」的间隔。
    """
    base = random.uniform(15, 60)
    typing = len(text) * random.uniform(0.05, 0.2)
    return min(base + typing, 90.0)


def send_message(
    chat_id: str,
    to_uid: str,
    text: str,
    *,
    humanize: bool = True,
    force_night: bool = False,
) -> None:
    """同步封装，供命令脚本调用。

    - humanize=True 时模拟人工输入延迟（15-90s）
    - 默认在夜间静默期 (XIANYU_QUIET_START~XIANYU_QUIET_END, 默认 01:00~07:30 CST)
      拒发，避免凌晨秒回的机器人特征。force_night=True 可绕过
    """
    if not force_night and _is_quiet_now():
        start, end = _quiet_window()
        raise QuietHoursError(
            f"当前在夜间静默期 ({start.strftime('%H:%M')}~{end.strftime('%H:%M')} CST)，"
            f"拒绝发送以避免机器人特征。"
            f"如确需发送，命令加 --force-night 或代码 send_message(..., force_night=True)。"
        )
    if humanize:
        delay = _humanize_delay(text)
        print(f"模拟人工输入，延迟 {delay:.2f}s 发送…")
        time.sleep(delay)
    asyncio.run(_send_once(chat_id, to_uid, text))


async def _fetch_history_once(chat_id: str, timeout: float = 30.0) -> list:
    cookies_str = _read_cookies()
    cookies = trans_cookies(cookies_str)
    my_uid = cookies["unb"]
    device_id = generate_device_id(my_uid)

    xianyu = XianyuApis()
    xianyu.session.cookies.update(cookies)
    token_result = xianyu.get_token(device_id)
    token = token_result["data"]["accessToken"]

    ws_headers = {
        "Cookie": cookies_str,
        "Host": "wss-goofish.dingtalk.com",
        "Connection": "Upgrade",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://www.goofish.com",
    }

    send_mid = generate_mid()
    list_msg = {
        "lwp": "/r/MessageManager/listUserMessages",
        "headers": {"mid": send_mid},
        "body": [f"{chat_id}@goofish", False, 9007199254740991, 50, False],
    }
    messages = []

    async def _inner(ws):
        nonlocal send_mid
        reg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": device_id,
                "mid": generate_mid(),
            },
        }
        await ws.send(json.dumps(reg))
        await asyncio.sleep(random.uniform(0.8, 1.6))
        ack_diff = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": "5701741704675979 0"},
            "body": [{
                "pipeline": "sync", "tooLong2Tag": "PNM,1", "channel": "sync",
                "topic": "sync", "highPts": 0,
                "pts": int(time.time() * 1000) * 1000,
                "seq": 0, "timestamp": int(time.time() * 1000),
            }],
        }
        await ws.send(json.dumps(ack_diff))

        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            hdr = msg.get("headers", {})

            # ack every message
            ack = {"code": 200, "headers": {
                "mid": hdr.get("mid", generate_mid()),
                "sid": hdr.get("sid", ""),
            }}
            for k in ("app-key", "ua", "dt"):
                if k in hdr:
                    ack["headers"][k] = hdr[k]
            try:
                await ws.send(json.dumps(ack))
            except Exception:
                pass

            # server ready → fire the list request
            if msg.get("lwp") == "/s/vulcan":
                await ws.send(json.dumps(list_msg))
                continue

            if hdr.get("mid") != send_mid:
                continue

            body = msg.get("body", {})
            for um in body.get("userMessageModels", []):
                try:
                    ext = um["message"]["extension"]
                    sender_uid = ext.get("senderUserId", "")
                    sender_name = ext.get("reminderTitle", "")
                    data_b64 = um["message"]["content"]["custom"]["data"]
                    content = json.loads(base64.b64decode(data_b64).decode())
                    ct = content.get("contentType", 0)
                    image_url = ""
                    if ct == 1:
                        text = content.get("text", {}).get("text", "")
                    elif ct == 2:
                        # 尝试抽 URL：常见路径 image.url / image.pics[0] / picUrl
                        img = content.get("image", {})
                        if isinstance(img, dict):
                            image_url = img.get("url") or img.get("picUrl") or ""
                            if not image_url:
                                pics = img.get("pics") or []
                                if pics and isinstance(pics, list):
                                    image_url = pics[0] if isinstance(pics[0], str) else pics[0].get("url", "")
                        text = f"[图片] {image_url}" if image_url else "[图片]"
                    else:
                        text = f"[type={ct}]"
                    messages.insert(0, {
                        "sender_uid": sender_uid,
                        "sender_name": sender_name,
                        "direction": "→" if sender_uid == my_uid else "←",
                        "text": text,
                        "content_type": ct,
                        "image_url": image_url,
                        "raw_content": content,
                    })
                except Exception:
                    pass

            if body.get("hasMore") == 1:
                send_mid = generate_mid()
                list_msg["headers"]["mid"] = send_mid
                list_msg["body"][2] = body["nextCursor"]
                await ws.send(json.dumps(list_msg))
            else:
                return

    async with websockets.connect(_WS_URL, extra_headers=ws_headers) as ws:
        await asyncio.wait_for(_inner(ws), timeout=timeout)

    return messages


def fetch_chat_history(chat_id: str, timeout: float = 30.0) -> list:
    """拉取指定会话全部历史消息，时间正序。

    每条消息：{"sender_uid", "sender_name", "direction"("←"买家/"→"你), "text", "content_type"}
    """
    return asyncio.run(_fetch_history_once(chat_id, timeout))
