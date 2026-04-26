"""
Travelpayouts (Aviasales) Flight Data API 客户端。

数据来自缓存（用户近 7 天历史搜索），非实时可订价，仅做参考。
origin/destination 用 IATA 三字码或城市码（SHA/BJS/TYO）。

接口：
  search_cheap(origin, destination, depart_month, return_month=None, currency="CNY")
    → list[dict]：price / airline / flight_number / departure_at / stops
  search_calendar(origin, destination, depart_month, currency="CNY")
    → list[dict]：按日期列出当月每天最低价
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT     = Path(__file__).parent.parent
_ENV_FILE = _ROOT / "config" / "travelpayouts.env"
_BASE     = "https://api.travelpayouts.com"


def _load_token() -> str:
    if not _ENV_FILE.exists():
        raise RuntimeError(
            f"找不到 {_ENV_FILE}。"
            "复制 config/travelpayouts.env.example 为 travelpayouts.env 填入 token。"
        )
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("TRAVELPAYOUTS_TOKEN"):
            _, v = line.split("=", 1)
            return v.strip()
    raise RuntimeError(f"{_ENV_FILE} 缺 TRAVELPAYOUTS_TOKEN")


def _get(path: str, params: dict) -> dict:
    token = _load_token()
    url = f"{_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "X-Access-Token": token,
        "Accept":         "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Travelpayouts API {e.code}: {body}") from e


def search_cheap(
    origin: str,
    destination: str,
    depart_month: str,
    return_month: str | None = None,
    currency: str = "CNY",
) -> list[dict]:
    """depart_month: YYYY-MM。返回按价格升序的列表。"""
    params = {
        "origin":      origin.upper(),
        "destination": destination.upper(),
        "depart_date": depart_month,
        "currency":    currency,
        "show_to_affiliates": "false",
    }
    if return_month:
        params["return_date"] = return_month

    data = _get("/v1/prices/cheap", params)
    if not data.get("success"):
        raise RuntimeError(f"API 返回失败：{data}")

    raw = data.get("data", {})
    results = []
    # raw 结构：{destination_code: {stops_count: {price, airline, ...}}}
    for dest_code, by_stops in raw.items():
        for stops_str, info in by_stops.items():
            results.append({
                "price":          info.get("price", 0),
                "currency":       currency,
                "airline":        info.get("airline", ""),
                "flight_number":  info.get("flight_number", ""),
                "departure_at":   info.get("departure_at", ""),
                "return_at":      info.get("return_at", ""),
                "stops":          int(stops_str),
                "destination":    dest_code,
            })

    results.sort(key=lambda r: r["price"])
    return results


def search_calendar(
    origin: str,
    destination: str,
    depart_month: str,
    currency: str = "CNY",
) -> list[dict]:
    """返回当月每天最低价，按日期排序。depart_month: YYYY-MM。"""
    params = {
        "origin":        origin.upper(),
        "destination":   destination.upper(),
        "depart_date":   depart_month,
        "currency":      currency,
        "calendar_type": "departure_date",
        "show_to_affiliates": "false",
    }
    data = _get("/v1/prices/calendar", params)
    if not data.get("success"):
        raise RuntimeError(f"API 返回失败：{data}")

    results = []
    for date_str, info in data.get("data", {}).items():
        results.append({
            "date":          date_str,
            "price":         info.get("price", 0),
            "currency":      currency,
            "airline":       info.get("airline", ""),
            "flight_number": info.get("flight_number", ""),
            "departure_at":  info.get("departure_at", ""),
            "stops":         info.get("transfers", 0),
        })
    results.sort(key=lambda r: r["date"])
    return results
