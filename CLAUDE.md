# 生活助手工作区

通用生活助手：闲鱼代订（主线）、视频剪辑、出行订票、脚本工具、随手备忘。

## 行为规则

- 不解释「为什么」除非我问
- 直接做，不说「我来帮你」
- 给建议带推荐项 + 一句理由，不只列选项
- 别迎合，方向错了直接说
- 中文标点全角，代码/路径里的符号保持原样
- 不加 emoji

## 通用工具

`ffmpeg`（视频/音频）、`imagemagick`（图片批处理）、`python3` + `openpyxl`（数据/Excel）。脚本默认存 `scripts/`，下次复用。

## 目录

- `tasks/` 待办、视频音频素材（短期工作产物）
- `notes/` 小抄、备忘（长期知识）
- `listings/` 闲鱼商品文案，命名 `{商品}-{日期}.md`
- `scripts/` 通用脚本（pdf_merge / img_compress / av_trim / 等）
- `state/orders/` 订单 JSON（每笔一个，文件名 = `xianyu_order_id`）
- `state/incoming/` 守护进程落盘事件（`chat_*.json` 私信，`pnr_*.json` 上游 PNR）
- `state/attachments/` 下载图片（护照、PNR 截图）
- `lib/` order_store / order_formatter / xianyu_client / tg_client
- `daemons/` xianyu_daemon.py（私信监听）, tg_listener.py（TG 群监听）
- `commands/` Claude 协作命令（见下）
- `vendor/xianyu_live/` XianyuAutoAgent 协议层快照（不改）
- `data/` 价格数据源（新干线票价等）
- `config/xianyu_cookies.txt` 闲鱼 Cookie（gitignore，过期需浏览器过滑块后重拿，要带 `x5sec`）
- `xianyu/ledger.xlsx` 台账
- `logs/` 守护进程日志

## 闲鱼业务

报价 = 携程价 × 0.75 抹零；下单成本 = 携程价 × 0.4；利润仅在「已发回执 / 已收货」状态计入台账。

新干线特殊：传 JR 官方 JPY 价（`data/shinkansen_fares.json`），脚本自动 ×1.05 markup ×汇率得到 Klook 客户参考价（CNY），再按 0.75 抹零 → `quote.py --jpy-price N`。汇率走 `lib/fx.py`，24h 缓存。

### 订单 JSON schema 关键字段

```text
xianyu_order_id, xianyu_chat_id
buyer.{nick, xianyu_uid}
item.{type=flight|hotel|rail, summary, xianyu_item_id}
trip.{origin, origin_code, destination, destination_code, is_round_trip,
      departure_date, return_date, departure_time, passenger_count,
      ticket_count, airline}
travelers[].{name_cn, name_en, gender, passport, passport_expiry, dob, nationality, baggage}
pricing.{ctrip_price, quoted_price, currency, source}
status   询价 | 已报价 | 已付款 | 已发单 | 已出票 | 已发回执 | 已收货 | 交易关闭
timeline[].{status, at, note}
fulfillment.{supplier_pnr, supplier_attachments, buyer_receipt_sent_at}
notes[]
```

`update_status / save / load / list_all` 在 `lib/order_store.py`，状态校验和 timeline 自动追加都封装好了。

### 命令（详细参数 `python commands/xxx.py -h`）

| 命令 | 用途 |
| --- | --- |
| `inbox.py [--all] [--mark-read]` | 列未处理事件，按会话分组，显示方向（← 买家 / → 你） |
| `quote.py --order-id X {--ctrip-price N \| --jpy-price N} [--ratio 0.75 \| --price N] [--markup 1.05]` | 报价草稿，写入 `pricing.quoted_price`，timeline 追加「已报价」 |
| `scripts/show_shinkansen.py FROM TO [SEAT]` | 查新干线 JR + Klook + 报价 一行（含 fuzzy 站名匹配） |
| `scripts/show_fx.py [--refresh] [--jpy N]` | 查 / 刷新 JPY→CNY 汇率 |
| `reply.py {--order-id X \| --chat-id Y --to-uid Z} --text "..." [--confirm]` | 闲鱼私信，无 `--confirm` 只 dry-run |
| `dispatch.py --order-id X [--confirm]` | 发到 TG 发单群，timeline 追加「已发单」 |
| `match_pnr.py [--pnr-file F --order-id X --pnr CODE [--confirm]]` | 关联上游 PNR 到订单，timeline 追加「已出票」 |
| `send_receipt.py --order-id X [--confirm]` | PNR 回执发买家，timeline 追加「已发回执」 |
| `mark.py {--order-id X --status S [--note N] \| --list-statuses}` | 手动推进状态（仅向前，无回滚） |
| `scripts/update_xianyu_ledger.py` | 刷新 `xianyu/ledger.xlsx` |

### 启动守护进程

```bash
nohup .venv/bin/python daemons/xianyu_daemon.py > logs/xianyu_daemon.log 2>&1 &
```

Cookie 过期日志会出 `RGV587_ERROR` / `被挤爆啦`。

### 闲鱼商品文案风格

真实、口语化，不堆砌形容词。说清楚品相、原价、出价理由。

## 视频处理默认参数

输出 mp4（H.264 + AAC），分辨率保持原始；脚本接收输入路径作为参数，输出到同目录 `{原文件名}_out.mp4`。
