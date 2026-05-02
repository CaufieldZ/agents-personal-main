"""
把结构化订单数据格式化成 Telegram 发单文本。

订单数据结构示例：
{
    "order_id": "XY20260426001",
    "items": [
        {
            "type": "flight",
            "origin": "香港",
            "origin_code": "HKG",
            "destination": "台北桃园",
            "destination_code": "TPE",
            "is_round_trip": true,
            "date": "2026-06-01 至 2026-06-05",
            "ctrip_price": "3200",
            "passengers": [
                {
                    "name_cn": "张三",
                    "name_en": "ZHANG SAN",
                    "gender": "男",
                    "passport": "E12345678",
                    "passport_expiry": "2030-01-01",
                    "dob": "1990-05-20",
                    "nationality": "中国",
                    "baggage": "1件20kg"
                }
            ]
        },
        {
            "type": "hotel",
            "name": "巴黎希尔顿酒店",
            "checkin": "2026-06-01",
            "checkout": "2026-06-03",
            "room_type": "豪华大床房",
            "guests": 2,
            "breakfast": "含早餐",
            "ctrip_price": "1500",
            "passengers": [...]
        },
        {
            "type": "rail",
            "route": "东京站 → 京都站",
            "date": "2026-06-01",
            "departure_time": "09:00",
            "is_round_trip": false,
            "ticket_count": 2,
            "price_source": "Klook",
            "ctrip_price": "800"
        }
    ]
}
"""


FORBIDDEN_PRICE_KEYS = {"deal_price", "xianyu_price", "sale_price", "成交价", "闲鱼成交价"}
PLACEHOLDER_VALUES = {"", "已识别", "待识别", "未知", "TBD", "N/A", "NA"}
REQUIRED_PASSENGER_FIELDS = {
    "name_cn": "中文姓名",
    "name_en": "英文姓名",
    "gender": "性别",
    "passport": "护照号",
    "passport_expiry": "护照有效期",
    "dob": "出生日期",
    "nationality": "国籍",
}


def validate_order(order: dict) -> None:
    forbidden = FORBIDDEN_PRICE_KEYS & set(order.keys())
    if forbidden:
        raise ValueError(f"发单群禁止包含闲鱼成交价字段：{', '.join(sorted(forbidden))}")

    for idx, item in enumerate(order.get("items", []), 1):
        forbidden = FORBIDDEN_PRICE_KEYS & set(item.keys())
        if forbidden:
            raise ValueError(f"第 {idx} 个项目禁止包含闲鱼成交价字段：{', '.join(sorted(forbidden))}")
        if item.get("type") in {"flight", "hotel", "rail"} and not item.get("ctrip_price"):
            raise ValueError(f"第 {idx} 个项目缺少原价 ctrip_price")
        for pidx, passenger in enumerate(item.get("passengers", []), 1):
            for field, label in REQUIRED_PASSENGER_FIELDS.items():
                value = str(passenger.get(field, "")).strip()
                if value in PLACEHOLDER_VALUES:
                    raise ValueError(f"第 {idx} 个项目旅客 {pidx} 缺少真实{label}")


def format_passenger(p: dict, include_baggage: bool = False) -> str:
    lines = [
        f"{p['name_cn']} / {p['name_en']}",
        f"性别：{p['gender']}",
        f"护照：{p['passport']}  有效期：{p['passport_expiry']}",
        f"出生日期：{p['dob']}  国籍：{p['nationality']}",
    ]
    if include_baggage and p.get("baggage"):
        lines.append(f"行李：{p['baggage']}")
    return "\n".join(lines)


def _route_str(item: dict) -> str:
    origin = item.get("origin") or ""
    dest   = item.get("destination") or ""
    o_code = item.get("origin_code") or ""
    d_code = item.get("destination_code") or ""

    if origin and dest:
        o = f"{origin}({o_code})" if o_code else origin
        d = f"{dest}({d_code})"   if d_code else dest
        arrow = "⇄" if item.get("is_round_trip") else "→"
        return f"{o} {arrow} {d}"

    return item.get("route") or ""


def format_flight(item: dict) -> str:
    lines = ["【机票】"]
    lines.append(f"航线：{_route_str(item)}")
    lines.append(f"日期：{item['date']}")
    lines.append("")
    for i, p in enumerate(item.get("passengers", []), 1):
        lines.append(f"旅客{i}：{format_passenger(p, include_baggage=True)}")
        if i < len(item["passengers"]):
            lines.append("")
    price_src = item.get("price_source", "携程")
    lines.append(f"{price_src}原价：{item['ctrip_price']}元")
    return "\n".join(lines)


def format_hotel(item: dict) -> str:
    lines = ["【酒店】"]
    lines.append(f"酒店名称：{item['name']}")
    lines.append(f"日期：{item['checkin']}～{item['checkout']}")
    if item.get("room_type"):
        lines.append(f"房型：{item['room_type']}")
    if item.get("guests"):
        lines.append(f"入住人数：{item['guests']}人")
    if item.get("breakfast"):
        lines.append(f"早餐：{item['breakfast']}")
    lines.append("入住人信息：")
    for p in item.get("passengers", []):
        lines.append(format_passenger(p))
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    price_src = item.get("price_source", "携程")
    lines.append(f"{price_src}原价：{item['ctrip_price']}元")
    return "\n".join(lines)


def format_rail(item: dict) -> str:
    lines = ["【铁路】"]
    lines.append(f"路线：{item['route']}")

    is_round = item.get("is_round_trip", False)
    if is_round:
        outbound = item.get("date") or ""
        return_d  = item.get("return_date") or ""
        lines.append(f"去程：{outbound}" + (f"  出发时间：{item['departure_time']}" if item.get("departure_time") else ""))
        if return_d:
            lines.append(f"返程：{return_d}" + (f"  出发时间：{item['return_departure_time']}" if item.get("return_departure_time") else ""))
    else:
        lines.append(f"日期：{item['date']}")
        if item.get("departure_time"):
            lines.append(f"出发时间：{item['departure_time']}")

    if item.get("ticket_count"):
        lines.append(f"张数：{item['ticket_count']}张")

    price_src = item.get("price_source", "携程")
    lines.append(f"{price_src}原价：{item['ctrip_price']}元")
    return "\n".join(lines)


def format_order(order: dict) -> str:
    validate_order(order)

    parts = []
    formatters = {
        "flight": format_flight,
        "hotel":  format_hotel,
        "rail":   format_rail,
    }
    for item in order.get("items", []):
        fn = formatters.get(item["type"])
        if fn:
            parts.append(fn(item))

    return "\n\n".join(parts)


if __name__ == "__main__":
    sample = {
        "items": [
            {
                "type": "flight",
                "origin": "北京",
                "origin_code": "PEK",
                "destination": "巴黎戴高乐",
                "destination_code": "CDG",
                "is_round_trip": True,
                "date": "2026-06-01 至 2026-06-10",
                "ctrip_price": "3200",
                "passengers": [
                    {
                        "name_cn": "张三",
                        "name_en": "ZHANG SAN",
                        "gender": "男",
                        "passport": "E12345678",
                        "passport_expiry": "2030-01-01",
                        "dob": "1990-05-20",
                        "nationality": "中国",
                        "baggage": "1件20kg",
                    }
                ],
            },
            {
                "type": "hotel",
                "name": "巴黎希尔顿酒店",
                "checkin": "2026-06-01",
                "checkout": "2026-06-03",
                "room_type": "豪华大床房",
                "guests": 2,
                "breakfast": "含早餐",
                "ctrip_price": "1500",
                "passengers": [
                    {
                        "name_cn": "张三",
                        "name_en": "ZHANG SAN",
                        "gender": "男",
                        "passport": "E12345678",
                        "passport_expiry": "2030-01-01",
                        "dob": "1990-05-20",
                        "nationality": "中国",
                    }
                ],
            },
            {
                "type": "rail",
                "route": "东京站 → 新大阪站",
                "date": "2026-06-05",
                "departure_time": "09:03",
                "is_round_trip": False,
                "ticket_count": 2,
                "price_source": "Klook",
                "ctrip_price": "800",
            },
        ],
    }
    print(format_order(sample))
