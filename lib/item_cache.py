"""
闲鱼商品信息 SQLite 缓存。

第一次查 item_id 时调用 XianyuApis 拉取并落库；后续直接读缓存。
默认 7 天 TTL，过期重新拉取。
"""

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "vendor" / "xianyu_live"))

_DB_PATH = _ROOT / "state" / "item_cache.db"
_TTL_SECONDS = 7 * 24 * 3600


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            title TEXT,
            price REAL,
            data TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    return conn


def _extract(api_result: dict) -> tuple[str, float, dict]:
    """从 mtop.taobao.idle.pc.detail 响应里抽 (title, price, item_do)。"""
    item_do = {}
    try:
        item_do = api_result["data"]["itemDO"] or {}
    except (KeyError, TypeError):
        pass
    title = str(item_do.get("title", "") or "")
    try:
        price = round(float(item_do.get("soldPrice", 0) or 0), 2)
    except (TypeError, ValueError):
        price = 0.0
    return title, price, item_do


def _fetch_remote(item_id: str) -> Optional[dict]:
    """实际去闲鱼拉商品详情。Cookie 过期会返回包含 error 的字典。"""
    from XianyuApis import XianyuApis  # noqa: E402
    from utils.xianyu_utils import trans_cookies, generate_device_id

    cookies_str = (_ROOT / "config" / "xianyu_cookies.txt").read_text(encoding="utf-8").strip()
    cookies = trans_cookies(cookies_str)
    api = XianyuApis()
    api.session.cookies.update(cookies)
    # get_token 会刷新 _m_h5_tk，get_item_info 内部要用
    api.get_token(generate_device_id(cookies["unb"]))
    return api.get_item_info(item_id)


def get(item_id: str, *, force_refresh: bool = False) -> Optional[dict]:
    """
    返回 {"item_id", "title", "price", "data", "updated_at", "from_cache"}。
    item_id 为空或拉取失败时返回 None。
    """
    if not item_id:
        return None

    now = int(time.time())
    with _conn() as conn:
        row = conn.execute(
            "SELECT title, price, data, updated_at FROM items WHERE item_id = ?",
            (item_id,),
        ).fetchone()

    if row and not force_refresh and (now - row[3]) < _TTL_SECONDS:
        return {
            "item_id": item_id,
            "title": row[0],
            "price": row[1],
            "data": json.loads(row[2]),
            "updated_at": row[3],
            "from_cache": True,
        }

    try:
        api_result = _fetch_remote(item_id)
    except Exception as e:
        # 网络/Cookie 异常时降级到旧缓存（如果有）
        if row:
            return {
                "item_id": item_id, "title": row[0], "price": row[1],
                "data": json.loads(row[2]), "updated_at": row[3],
                "from_cache": True, "stale": True, "error": str(e),
            }
        return None

    if not api_result or "error" in api_result:
        if row:
            return {
                "item_id": item_id, "title": row[0], "price": row[1],
                "data": json.loads(row[2]), "updated_at": row[3],
                "from_cache": True, "stale": True,
            }
        return None

    title, price, _ = _extract(api_result)
    data_json = json.dumps(api_result, ensure_ascii=False)
    with _conn() as conn:
        conn.execute("""
            INSERT INTO items (item_id, title, price, data, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                title = excluded.title,
                price = excluded.price,
                data  = excluded.data,
                updated_at = excluded.updated_at
        """, (item_id, title, price, data_json, now))
        conn.commit()

    return {
        "item_id": item_id, "title": title, "price": price,
        "data": api_result, "updated_at": now, "from_cache": False,
    }


def get_title(item_id: str) -> str:
    """快捷：只要标题，缓存里有就直接出，没有就拉一次。失败返回空串。"""
    info = get(item_id)
    return info["title"] if info else ""
