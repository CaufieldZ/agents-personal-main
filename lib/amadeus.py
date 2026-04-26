"""
Amadeus Self-Service API 客户端：航班价格查询。

凭证：config/amadeus.env（gitignore），格式：
  AMADEUS_CLIENT_ID=xxx
  AMADEUS_CLIENT_SECRET=xxx
  AMADEUS_ENV=production           # 或 test，默认 production
  AMADEUS_DEFAULT_CURRENCY=CNY     # 可选

接口：
  search_flights(origin, destination, depart_date, return_date=None,
                 adults=1, currency=None, max_results=5, non_stop=False)
    → list[dict]：每个 dict 含 price / carrier / itinerary / segments
  get_token() / refresh_token() → 内部用，token 缓存 data/amadeus_token.json

文档：https://developers.amadeus.com/self-service/category/flights/api-doc/flight-offers-search
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT       = Path(__file__).parent.parent
_ENV_FILE   = _ROOT / "config" / "amadeus.env"
_TOKEN_FILE = _ROOT / "data" / "amadeus_token.json"

_HOSTS = {
    "test":       "https://test.api.amadeus.com",
    "production": "https://api.amadeus.com",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_env() -> dict:
    if not _ENV_FILE.exists():
        raise RuntimeError(
            f"找不到 {_ENV_FILE}。先注册 https://developers.amadeus.com/ "
            f"创建 Self-Service App，复制 config/amadeus.env.example 为 amadeus.env "
            f"填入 client_id / client_secret。"
        )
    env = {}
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    if "AMADEUS_CLIENT_ID" not in env or "AMADEUS_CLIENT_SECRET" not in env:
        raise RuntimeError(f"{_ENV_FILE} 缺 AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET")
    return env


def _host() -> str:
    env = _load_env()
    name = env.get("AMADEUS_ENV", "production").lower()
    if name not in _HOSTS:
        raise RuntimeError(f"AMADEUS_ENV 必须是 test 或 production，当前 {name!r}")
    return _HOSTS[name]


def _load_token() -> dict | None:
    if not _TOKEN_FILE.exists():
        return None
    try:
        payload = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        expires_at = datetime.fromisoformat(payload["expires_at"])
    except Exception:
        return None
    # 留 60s 余量
    if _now() >= expires_at - timedelta(seconds=60):
        return None
    if payload.get("host") != _host():
        return None
    return payload


def _save_token(access_token: str, expires_in: int) -> dict:
    payload = {
        "access_token": access_token,
        "expires_at":   (_now() + timedelta(seconds=expires_in)).isoformat(),
        "host":         _host(),
    }
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def refresh_token() -> str:
    env = _load_env()
    body = urllib.parse.urlencode({
        "grant_type":    "client_credentials",
        "client_id":     env["AMADEUS_CLIENT_ID"],
        "client_secret": env["AMADEUS_CLIENT_SECRET"],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{_host()}/v1/security/oauth2/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    payload = _save_token(data["access_token"], int(data["expires_in"]))
    return payload["access_token"]


def get_token() -> str:
    cached = _load_token()
    if cached:
        return cached["access_token"]
    return refresh_token()


def _request(path: str, params: dict, retry_on_401: bool = True) -> dict:
    url = f"{_host()}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {get_token()}",
        "Accept":        "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry_on_401:
            refresh_token()
            return _request(path, params, retry_on_401=False)
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Amadeus API {e.code}: {body}") from e


def _flatten_offer(offer: dict, dictionaries: dict) -> dict:
    price = offer["price"]
    carriers = dictionaries.get("carriers", {})

    itineraries = []
    all_segments = []
    for itin in offer["itineraries"]:
        segs = []
        for s in itin["segments"]:
            seg = {
                "carrier":      s["carrierCode"],
                "carrier_name": carriers.get(s["carrierCode"], s["carrierCode"]),
                "flight":       f"{s['carrierCode']}{s['number']}",
                "depart":       f"{s['departure']['iataCode']} {s['departure']['at']}",
                "arrive":       f"{s['arrival']['iataCode']} {s['arrival']['at']}",
                "duration":     s.get("duration", ""),
            }
            segs.append(seg)
            all_segments.append(seg)
        itineraries.append({"duration": itin.get("duration", ""), "segments": segs})

    return {
        "price":        float(price["grandTotal"]),
        "currency":     price["currency"],
        "stops":        sum(len(it["segments"]) - 1 for it in offer["itineraries"]),
        "itineraries":  itineraries,
        "segments":     all_segments,
        "validating_carriers": offer.get("validatingAirlineCodes", []),
    }


def search_flights(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str | None = None,
    adults: int = 1,
    currency: str | None = None,
    max_results: int = 5,
    non_stop: bool = False,
) -> list[dict]:
    """origin/destination 用 IATA 三字码（PEK / NRT）。日期 YYYY-MM-DD。"""
    env = _load_env()
    if currency is None:
        currency = env.get("AMADEUS_DEFAULT_CURRENCY", "CNY")
    params = {
        "originLocationCode":      origin.upper(),
        "destinationLocationCode": destination.upper(),
        "departureDate":           depart_date,
        "adults":                  adults,
        "currencyCode":            currency,
        "max":                     max_results,
        "nonStop":                 "true" if non_stop else "false",
    }
    if return_date:
        params["returnDate"] = return_date

    data = _request("/v2/shopping/flight-offers", params)
    offers = data.get("data", [])
    dictionaries = data.get("dictionaries", {})
    return [_flatten_offer(o, dictionaries) for o in offers]
