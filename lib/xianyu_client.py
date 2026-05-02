"""
轻量闲鱼发消息客户端。

每次调用 send_message 都开一个短连接：登录 → 注册 → 发消息 → 断开。
仅用于命令脚本（commands/reply.py 等），不是守护进程。
"""

import asyncio
import base64
import json
import sys
import time
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
        await asyncio.sleep(1)

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
        await asyncio.sleep(0.5)

        # 发送消息
        payload = _build_text_payload(chat_id, to_uid, my_uid, text)
        await ws.send(payload)
        await asyncio.sleep(0.5)


def send_message(chat_id: str, to_uid: str, text: str) -> None:
    """同步封装，供命令脚本调用。"""
    asyncio.run(_send_once(chat_id, to_uid, text))
