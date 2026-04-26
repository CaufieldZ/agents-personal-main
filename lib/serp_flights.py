"""
SerpAPI Google Flights 客户端：参考价查询。

凭证：config/serpapi.env，格式：
  SERPAPI_KEY=xxx

接口：
  search_flights(origin, destination, depart_date, return_date=None,
                 adults=1, currency="CNY", travel_class=1, max_results=5)
    → list[dict]：每条含 price / currency / stops / itineraries / segments
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT     = Path(__file__).parent.parent
_ENV_FILE = _ROOT / "config" / "serpapi.env"
_BASE_URL = "https://serpapi.com/search"


def _load_key() -> str:
    if not _ENV_FILE.exists():
        raise RuntimeError(
            f"找不到 {_ENV_FILE}。"
            "注册 https://serpapi.com/ 拿 API Key，"
            "复制 config/serpapi.env.example 为 serpapi.env 填入 SERPAPI_KEY=xxx。"
        )
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("SERPAPI_KEY"):
            _, v = line.split("=", 1)
            return v.strip().strip('"').strip("'")
    raise RuntimeError(f"{_ENV_FILE} 缺 SERPAPI_KEY")


def _fmt_duration(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h{m:02d}m"


def _flatten_offer(result: dict, currency: str) -> dict:
    segments = []
    for s in result.get("flights", []):
        segments.append({
            "flight":        s.get("flight_number", "?"),
            "carrier":       s.get("airline", ""),
            "depart":        f"{s['departure_airport']['id']} {s['departure_airport']['time']}",
            "arrive":        f"{s['arrival_airport']['id']} {s['arrival_airport']['time']}",
            "duration":      _fmt_duration(s.get("duration", 0)),
        })

    stops = max(0, len(segments) - 1)
    total_dur = _fmt_duration(result.get("total_duration", 0))

    return {
        "price":       float(result.get("price", 0)),
        "currency":    currency,
        "stops":       stops,
        "itineraries": [{"duration": total_dur, "segments": segments}],
        "segments":    segments,
    }


def search_flights(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str | None = None,
    adults: int = 1,
    currency: str = "CNY",
    travel_class: int = 1,
    max_results: int = 5,
    non_stop: bool = False,
) -> list[dict]:
    """origin/destination 用 IATA 三字码。日期 YYYY-MM-DD。travel_class: 1=经济 2=超经 3=商务 4=头等。"""
    key = _load_key()
    params = {
        "engine":         "google_flights",
        "departure_id":   origin.upper(),
        "arrival_id":     destination.upper(),
        "outbound_date":  depart_date,
        "adults":         adults,
        "currency":       currency,
        "travel_class":   travel_class,
        "type":           1 if return_date else 2,  # 1=往返 2=单程
        "hl":             "en",
        "gl":             "us",
        "api_key":        key,
        "no_cache":       "false",
    }
    if return_date:
        params["return_date"] = return_date
    if non_stop:
        params["stops"] = 0

    url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "agents-cli/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SerpAPI {e.code}: {body}") from e

    if "error" in data:
        raise RuntimeError(f"SerpAPI 返回错误：{data['error']}")

    results = data.get("best_flights", []) + data.get("other_flights", [])
    if not results:
        return []

    offers = [_flatten_offer(r, currency) for r in results]
    if non_stop:
        offers = [o for o in offers if o["stops"] == 0]

    offers.sort(key=lambda o: o["price"])
    return offers[:max_results]
