"""
JPY → CNY 汇率，24h 缓存，含 1.5% 缓冲。

接口：
  get_jpy_to_cny()        → 缓冲后汇率（实际报价用）
  get_jpy_to_cny_mid()    → 中间价（仅参考）
  refresh()               → 强制刷新
  jpy_to_cny(jpy)         → JPY 数额换算成 CNY（含缓冲）

数据源：open.er-api.com（免费、无 key、日更）
缓存：data/fx_rate.json
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT       = Path(__file__).parent.parent
_CACHE_FILE = _ROOT / "data" / "fx_rate.json"
_API_URL    = "https://open.er-api.com/v6/latest/JPY"
_TTL_HOURS  = 24
_BUFFER     = 1.015


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fetch() -> dict:
    req = urllib.request.Request(_API_URL, headers={"User-Agent": "agents-cli/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("result") != "success":
        raise RuntimeError(f"FX API failed: {data}")
    rate = data["rates"]["CNY"]
    return {
        "jpy_cny_mid":  rate,
        "fetched_at":   _now().isoformat(),
        "source":       "open.er-api.com",
        "source_date":  data.get("time_last_update_utc", ""),
    }


def _load_cache() -> dict | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(payload: dict) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_fresh(payload: dict) -> bool:
    try:
        fetched = datetime.fromisoformat(payload["fetched_at"])
    except Exception:
        return False
    return _now() - fetched < timedelta(hours=_TTL_HOURS)


def refresh() -> dict:
    payload = _fetch()
    _save_cache(payload)
    return payload


def _get_payload(force_refresh: bool = False) -> dict:
    if not force_refresh:
        cached = _load_cache()
        if cached and _is_fresh(cached):
            return cached
    return refresh()


def get_jpy_to_cny_mid(force_refresh: bool = False) -> float:
    return _get_payload(force_refresh)["jpy_cny_mid"]


def get_jpy_to_cny(force_refresh: bool = False) -> float:
    return get_jpy_to_cny_mid(force_refresh) * _BUFFER


def jpy_to_cny(jpy: float, force_refresh: bool = False) -> float:
    return jpy * get_jpy_to_cny(force_refresh)
