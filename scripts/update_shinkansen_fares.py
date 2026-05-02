#!/usr/bin/env python3
"""
新干线票价更新脚本。
每年 4 月 JR 调价后运行一次，自动从第三方票价汇总站抓取最新价格并刷新 data/shinkansen_fares.json。

数据源：
  - https://jr-shinkansen.net/articles/fare-nozomi/   东海道·山阳 Nozomi 矩阵（运費+指定+自由）
  - https://shinkansen.tabiris.com/fare05.html        东北（东京発）
  - https://shinkansen.tabiris.com/fare06.html        上越（东京発）
  - https://shinkansen.tabiris.com/fare07.html        北陆（东京発）
  - https://shinkansen.tabiris.com/fare20.html        山阳+九州（新大阪発）
  - https://shinkansen.tabiris.com/fare24.html        九州新干线（博多発）
  - https://shinkansen.tabiris.com/green-fare02.html  东海道·山阳 绿色车厢（东京発）
  - https://shinkansen.tabiris.com/green-fare05.html  东北 绿色车厢（东京発）
  - https://shinkansen.tabiris.com/green-fare07.html  北陆 绿色车厢（东京発）
  - https://shinkansen.tabiris.com/green-fare06.html  上越 绿色车厢（东京発）

用法：
  python3 scripts/update_shinkansen_fares.py [--dry-run]
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("需要 requests：pip install requests")

OUT_FILE = Path(__file__).parent.parent / "data" / "shinkansen_fares.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# 東海道·山陽 グリーン料金 distance tiers（JR 官方距離段）
_GREEN_TIERS = [(100, 1300), (200, 2800), (400, 4190), (600, 5400), (800, 6600)]
_GREEN_TIERS_MAX = 7790

# 各站距东京的営業キロ（東海道·山陽方向）
_KM_FROM_TOKYO: dict[str, float] = {
    "名古屋":   366.0,
    "京都":     513.6,
    "新大阪":   552.6,
    "新神戸":   588.5,
    "岡山":     732.9,
    "広島":     894.2,
    "博多":    1069.1,
}


def _green_tier(km: float) -> int:
    for limit, fee in _GREEN_TIERS:
        if km <= limit:
            return fee
    return _GREEN_TIERS_MAX


def green_tokaido(reserved: int, from_cn: str, to_cn: str) -> int | None:
    """
    東海道·山陽 Nozomi グリーン車合計：reserved + グリーン料金(区間距離) - 530
    -530 は Hikari 指定席加算分（Nozomi reserved に含まれる基本指定席料金）の相殺。
    """
    km_from = _KM_FROM_TOKYO.get(from_cn)
    km_to   = _KM_FROM_TOKYO.get(to_cn)
    if km_from is None or km_to is None:
        return None
    km = abs(km_to - km_from)
    return reserved + _green_tier(km) - 530


# ─── 抓取工具 ────────────────────────────────────────────────────────────────

def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")


def parse_table(html: str) -> list[list[str]]:
    """把 HTML 里第一个 <table> 解析成 list[list[str]]（行 × 列）。"""
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    result = []
    for row in rows:
        cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).replace('&#8212;', '-').strip() for c in cells]
        cells = [re.sub(r'\s+', ' ', c).strip() for c in cells]
        if any(c for c in cells):
            result.append(cells)
    return result


def table_to_dict(rows: list[list[str]]) -> dict[str, list[str]]:
    """
    把带表头行的票价表转成 {站名: [col1, col2, ...]} 字典。
    第一行是表头（跳过），第一列是站名。
    """
    d = {}
    for row in rows[1:]:
        if not row or not row[0] or row[0] in ('駅名',):
            continue
        station = row[0].replace(' ', '')
        d[station] = row[1:]
    return d


def int_or_none(s: str) -> int | None:
    s = s.strip().replace(',', '').replace('*', '').replace('※', '')
    if s in ('-', '--', ''):
        return None
    try:
        return int(s)
    except ValueError:
        return None


# ─── 东海道·山阳 Nozomi 矩阵 ─────────────────────────────────────────────────

def fetch_nozomi_matrix() -> dict[tuple[str, str], dict]:
    """
    返回 {(from_station, to_station): {reserved, free}} 字典。
    reserved = Nozomi 指定席总价（运費+特急料金）
    free = 自由席总价
    矩阵格式每格：'运費 Nozomi指定席特急料金 自由席特急料金'
    """
    html = fetch("https://jr-shinkansen.net/articles/fare-nozomi/")
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

    # 站名行（th 内容）
    stations = []
    fares: dict[tuple[str, str], dict] = {}

    for row in rows:
        cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).replace('&#8212;', '-').strip() for c in cells]
        cells = [re.sub(r'\s+', ' ', c).strip() for c in cells]
        cells = [c for c in cells]

        if not cells:
            continue

        # 识别表头行
        if cells[0] == '駅名':
            raw_stations = [c.replace(' ', '') for c in cells[1:] if c and c != '駅名']
            if raw_stations:
                stations = raw_stations
            continue

        from_stn = cells[0].replace(' ', '')
        if not from_stn or from_stn == '駅名':
            continue

        for j, cell in enumerate(cells[1:]):
            if j >= len(stations):
                break
            to_stn = stations[j]
            if cell == '-':
                continue
            parts = cell.split()
            if len(parts) != 3:
                continue
            base, nozomi_sup, free_sup = [int_or_none(p) for p in parts]
            if base is None:
                continue
            reserved = (base + nozomi_sup) if nozomi_sup else None
            free = (base + free_sup) if free_sup else None
            fares[(from_stn, to_stn)] = {"reserved": reserved, "free": free}
            fares[(to_stn, from_stn)] = {"reserved": reserved, "free": free}

    return fares


# ─── Tabiris 单列票价表 ──────────────────────────────────────────────────────

def fetch_tabiris(url: str) -> dict[str, list[int | None]]:
    """
    返回 {站名: [col0_price, col1_price, ...]}，价格已为整数（None 表示不适用）。
    """
    html = fetch(url)
    rows = parse_table(html)
    d = {}
    for row in rows[1:]:
        if not row or not row[0] or row[0] in ('駅名',):
            continue
        station = row[0].replace(' ', '')
        prices = [int_or_none(v) for v in row[1:]]
        d[station] = prices
    return d


def lookup(d: dict[str, list], station: str, col: int = 0) -> int | None:
    station = station.replace(' ', '')
    if station not in d:
        return None
    vals = d[station]
    return vals[col] if col < len(vals) else None


# ─── 路线定义 ────────────────────────────────────────────────────────────────

def build_routes(
    nozomi: dict,
    tk_green: dict,       # 东京発 绿色车厢（东海道·山阳）
    shinos: dict,         # 新大阪発 山阳+九州
    hakata_san: dict,     # 博多発 山阳
    hakata_kyu: dict,     # 博多発 九州
    tohoku: dict,         # 东京発 东北
    grn_tohoku: dict,     # 东京発 东北绿色
    hokuriku: dict,       # 东京発 北陆
    grn_hokuriku: dict,   # 东京発 北陆绿色
    joetsu: dict,         # 东京発 上越
    grn_joetsu: dict,     # 东京発 上越绿色
) -> list[dict]:

    def noz(f, t):
        return nozomi.get((f, t), {})

    def r(fare_dict, key="reserved"):
        return fare_dict.get(key)

    routes = []

    def add(from_cn, from_jr, to_cn, to_jr, line, duration_min,
            free, reserved, green, granclass=None):
        routes.append({
            "from": from_cn, "from_jr": from_jr,
            "to": to_cn,     "to_jr": to_jr,
            "line": line,
            "fare": {
                "free": free,
                "reserved": reserved,
                "green": green,
                "granclass": granclass,
            },
            "child_ratio": 0.5,
            "duration_min": duration_min,
        })

    # ── 东海道 ──────────────────────────────────────────────────────────────
    # Tokyo → Nagoya
    nf = noz('東京品川', '名古屋')
    add("东京", "Tokyo", "名古屋", "Nagoya", "东海道新干线", 100,
        free=r(nf, "free"), reserved=r(nf, "reserved"),
        green=lookup(tk_green, '名古屋', 0))

    # Tokyo → Kyoto
    nf = noz('東京品川', '京都')
    add("东京", "Tokyo", "京都", "Kyoto", "东海道新干线", 135,
        free=r(nf, "free"), reserved=r(nf, "reserved"),
        green=lookup(tk_green, '京都', 0))

    # Tokyo → Shin-Osaka
    nf = noz('東京品川', '新大阪')
    add("东京", "Tokyo", "新大阪", "Shin-Osaka", "东海道新干线", 152,
        free=r(nf, "free"), reserved=r(nf, "reserved"),
        green=lookup(tk_green, '新大阪', 0))

    # Tokyo → Hiroshima
    nf = noz('東京品川', '広島')
    add("东京", "Tokyo", "广岛", "Hiroshima", "东海道·山阳新干线", 245,
        free=r(nf, "free"), reserved=r(nf, "reserved"),
        green=lookup(tk_green, '広島', 0))

    # Tokyo → Hakata
    nf = noz('東京品川', '博多')
    add("东京", "Tokyo", "博多", "Hakata", "东海道·山阳新干线", 305,
        free=r(nf, "free"), reserved=r(nf, "reserved"),
        green=lookup(tk_green, '博多', 0))

    # Nagoya → Kyoto
    nf = noz('名古屋', '京都')
    _res = r(nf, "reserved")
    add("名古屋", "Nagoya", "京都", "Kyoto", "东海道新干线", 35,
        free=r(nf, "free"), reserved=_res,
        green=green_tokaido(_res, "名古屋", "京都") if _res else None)

    # Nagoya → Shin-Osaka
    nf = noz('名古屋', '新大阪')
    _res = r(nf, "reserved")
    add("名古屋", "Nagoya", "新大阪", "Shin-Osaka", "东海道新干线", 50,
        free=r(nf, "free"), reserved=_res,
        green=green_tokaido(_res, "名古屋", "新大阪") if _res else None)

    # Kyoto → Shin-Osaka
    nf = noz('京都', '新大阪')
    _res = r(nf, "reserved")
    add("京都", "Kyoto", "新大阪", "Shin-Osaka", "东海道新干线", 15,
        free=r(nf, "free"), reserved=_res,
        green=green_tokaido(_res, "京都", "新大阪") if _res else None)

    # ── 山阳 ────────────────────────────────────────────────────────────────
    # Shin-Osaka → Okayama  （新大阪発 col0=Nozomi reserved）
    _res = lookup(shinos, '岡山', 0)
    add("新大阪", "Shin-Osaka", "冈山", "Okayama", "山阳新干线", 45,
        free=lookup(shinos, '岡山', 2), reserved=_res,
        green=green_tokaido(_res, "新大阪", "岡山") if _res else None)

    # Shin-Osaka → Hiroshima
    _res = lookup(shinos, '広島', 0)
    add("新大阪", "Shin-Osaka", "广岛", "Hiroshima", "山阳新干线", 75,
        free=lookup(shinos, '広島', 2), reserved=_res,
        green=green_tokaido(_res, "新大阪", "広島") if _res else None)

    # Shin-Osaka → Hakata
    _res = lookup(shinos, '博多', 0)
    add("新大阪", "Shin-Osaka", "博多", "Hakata", "山阳新干线", 135,
        free=lookup(shinos, '博多', 2), reserved=_res,
        green=green_tokaido(_res, "新大阪", "博多") if _res else None)

    # Okayama → Hiroshima  （博多発表：博多→广岛 - 博多→冈山 不是合法减法，用矩阵）
    nf = noz('岡山', '広島')
    _res = r(nf, "reserved")
    add("冈山", "Okayama", "广岛", "Hiroshima", "山阳新干线", 34,
        free=r(nf, "free"), reserved=_res,
        green=green_tokaido(_res, "岡山", "広島") if _res else None)

    # Hiroshima → Hakata
    nf = noz('広島', '博多')
    _res = r(nf, "reserved")
    add("广岛", "Hiroshima", "博多", "Hakata", "山阳新干线", 70,
        free=r(nf, "free"), reserved=_res,
        green=green_tokaido(_res, "広島", "博多") if _res else None)

    # ── 九州 ────────────────────────────────────────────────────────────────
    # Hakata → Kumamoto  （col0=指定席, col1=自由席）
    add("博多", "Hakata", "熊本", "Kumamoto", "九州新干线", 33,
        free=lookup(hakata_kyu, '熊本', 1), reserved=lookup(hakata_kyu, '熊本', 0),
        green=None)

    # Hakata → Kagoshima-Chuo
    add("博多", "Hakata", "鹿儿岛中央", "Kagoshima-Chuo", "九州新干线", 80,
        free=lookup(hakata_kyu, '鹿児島中央', 1), reserved=lookup(hakata_kyu, '鹿児島中央', 0),
        green=None)

    # Kumamoto → Kagoshima-Chuo  —— tabiris 无直接表，用新大阪発表反算
    # 新大阪→熊本 & 新大阪→鹿児島中央 的差值不等于区间票价；实际从 jr-shinkansen 矩阵取
    # Kyushu 矩阵（jr-shinkansen.net/articles/fare-kyushu/）单元格格式：运費/特急料金
    # 熊本→鹿児島中央: 3740/4230，但该矩阵可能非最新，暂留 null 待手动核查
    add("熊本", "Kumamoto", "鹿儿岛中央", "Kagoshima-Chuo", "九州新干线", 48,
        free=None, reserved=None, green=None)

    # ── 东北 + 北海道 ────────────────────────────────────────────────────────
    # Tokyo → Sendai  （col0=はやぶさ指定席, col1=やまびこ指定席, col2=自由席）
    add("东京", "Tokyo", "仙台", "Sendai", "东北新干线", 91,
        free=lookup(tohoku, '仙台', 2), reserved=lookup(tohoku, '仙台', 0),
        green=lookup(grn_tohoku, '仙台', 0))

    # Tokyo → Morioka
    add("东京", "Tokyo", "盛冈", "Morioka", "东北新干线", 120,
        free=lookup(tohoku, '盛岡', 2), reserved=lookup(tohoku, '盛岡', 0),
        green=lookup(grn_tohoku, '盛岡', 0))

    # Tokyo → Shin-Aomori
    add("东京", "Tokyo", "新青森", "Shin-Aomori", "东北新干线", 180,
        free=None, reserved=lookup(tohoku, '新青森', 0),
        green=lookup(grn_tohoku, '新青森', 0))

    # Tokyo → Shin-Hakodate-Hokuto
    add("东京", "Tokyo", "新函馆北斗", "Shin-Hakodate-Hokuto", "北海道新干线", 248,
        free=None, reserved=lookup(tohoku, '新函館北斗', 0),
        green=lookup(grn_tohoku, '新函館北斗', 0))

    # ── 北陆 ────────────────────────────────────────────────────────────────
    # Tokyo → Nagano
    add("东京", "Tokyo", "长野", "Nagano", "北陆新干线", 80,
        free=lookup(hokuriku, '長野', 1), reserved=lookup(hokuriku, '長野', 0),
        green=lookup(grn_hokuriku, '長野', 0))

    # Tokyo → Toyama
    add("东京", "Tokyo", "富山", "Toyama", "北陆新干线", 118,
        free=lookup(hokuriku, '富山', 1), reserved=lookup(hokuriku, '富山', 0),
        green=lookup(grn_hokuriku, '富山', 0))

    # Tokyo → Kanazawa
    add("东京", "Tokyo", "金泽", "Kanazawa", "北陆新干线", 133,
        free=lookup(hokuriku, '金沢', 1), reserved=lookup(hokuriku, '金沢', 0),
        green=lookup(grn_hokuriku, '金沢', 0))

    # Kanazawa → Toyama  —— 北陆矩阵：金沢→富山 = 990/2400 (运費/特急料金)
    # 合計: 指定席=990+2400=3390, 自由席=(990+2400-530)=2860
    # (北陆无自由席，北陆指定席 = 唯一选择)
    add("金泽", "Kanazawa", "富山", "Toyama", "北陆新干线", 22,
        free=None, reserved=3390, green=None)

    # ── 上越 ────────────────────────────────────────────────────────────────
    # Tokyo → Niigata  （col0=指定席, col1=自由席）
    add("东京", "Tokyo", "新潟", "Niigata", "上越新干线", 100,
        free=lookup(joetsu, '新潟', 1), reserved=lookup(joetsu, '新潟', 0),
        green=lookup(grn_joetsu, '新潟', 0))

    return routes


# ─── 主流程 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只输出 JSON，不写文件")
    args = parser.parse_args()

    print("正在抓取票价数据...", file=sys.stderr)

    nozomi     = fetch_nozomi_matrix()
    tk_green   = fetch_tabiris("https://shinkansen.tabiris.com/green-fare02.html")
    shinos     = fetch_tabiris("https://shinkansen.tabiris.com/fare20.html")
    hakata_san = fetch_tabiris("https://shinkansen.tabiris.com/fare23.html")
    hakata_kyu = fetch_tabiris("https://shinkansen.tabiris.com/fare24.html")
    tohoku     = fetch_tabiris("https://shinkansen.tabiris.com/fare05.html")
    grn_tohoku = fetch_tabiris("https://shinkansen.tabiris.com/green-fare05.html")
    hokuriku   = fetch_tabiris("https://shinkansen.tabiris.com/fare07.html")
    grn_hokuriku = fetch_tabiris("https://shinkansen.tabiris.com/green-fare07.html")
    joetsu       = fetch_tabiris("https://shinkansen.tabiris.com/fare06.html")
    grn_joetsu   = fetch_tabiris("https://shinkansen.tabiris.com/green-fare06.html")

    print("解析完成，生成路线数据...", file=sys.stderr)

    routes = build_routes(
        nozomi, tk_green, shinos, hakata_san, hakata_kyu,
        tohoku, grn_tohoku, hokuriku, grn_hokuriku, joetsu, grn_joetsu,
    )

    # 汇报空值
    null_count = sum(
        1 for ro in routes
        for v in ro["fare"].values() if v is None
    )
    print(f"路线数：{len(routes)}，空值字段：{null_count}", file=sys.stderr)
    for ro in routes:
        nulls = [k for k, v in ro["fare"].items() if v is None]
        if nulls:
            print(f"  {ro['from']}→{ro['to']}: null={nulls}", file=sys.stderr)

    output = {
        "updated_at": str(date.today()),
        "note": (
            "运賃 = 乗車券 + 特急券，成人价，通常期正規料金。"
            "reserved = Nozomi/はやぶさ/かがやき 指定席（最贵快车）。"
            "每年 4 月运行此脚本更新。"
        ),
        "routes": routes,
    }

    if args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        OUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
