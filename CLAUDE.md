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

脚本默认存 `scripts/`，下次复用。

### Office 全家桶
- **Word** `python-docx` — 读/写/改 .docx，按段落/表格/样式操作
- **Excel** `openpyxl` — 读/写/改 .xlsx，公式/样式/图表
- **PowerPoint** `python-pptx` — 读/写/改 .pptx，幻灯片/形状/文本框
- **格式转换** `pandoc` — docx/md/html/pdf/rst 互转

**Excel/openpyxl 输出验证**：用 WPS / Numbers / Excel 打开，VSCode 内置 xlsx 预览不渲染样式（字体/颜色/列宽/超链接全丢），别根据 VSCode 截图判断「丑」。

### 音视频
- `ffmpeg` — 转码/裁切/合并/字幕/滤镜/提取音频
- `ffprobe` — 查看元信息（编码/码率/分辨率/时长）

### Adobe 替代 / PDF
- `gs` (Ghostscript) — PDF 压缩/合并/加密码/转图片
- `qpdf` — PDF 拆分/合并/旋转/加密/解密/线性化
- `pdfplumber` (Python) — 提取文字/表格（比 pdfminer 准）
- `exiftool` — 读/写 EXIF/IPTC/XMP 元数据（图片/视频/PDF 均可）

### 图片
- `imagemagick` (convert/magick) — 格式转换/缩放/裁剪/加水印/批处理
- `pillow` (PIL, Python) — 像素级操作/合成/调色/OCR 预处理

## 目录

- `tasks/` 待办、视频音频素材（短期工作产物）
- `notes/` 小抄、备忘（长期知识）
- `listings/` 闲鱼商品文案，命名 `{商品}-{日期}.md`
- `scripts/` 通用脚本
- `state/orders/` 订单 JSON（每笔一个，文件名 = `xianyu_order_id`）
- `state/incoming/` 守护进程落盘事件（`chat_*.json` 私信，`pnr_*.json` 上游 PNR）
- `state/attachments/` 下载图片；上游 TG 走 `chat_<id>/`，手动 attach 走 `orders/<order-id>/`
- `lib/` order_store / order_formatter / xianyu_client / tg_client / fx / tp_flights
- `daemons/` xianyu_daemon.py（私信监听）, tg_listener.py（TG 群监听）
- `commands/` Claude 协作命令（见下）
- `vendor/xianyu_live/` XianyuAutoAgent 协议层快照。原则上不改，但已打两个本地补丁：(1) `XianyuApis.py` 风控触发改成落 `state/cookie_dirty.flag` + TG 告警 + `sys.exit(2)`，避免 nohup 下死循环；(2) `main.py` 心跳/Token 刷新/重连等待全部加抖动
- `data/` 价格数据源（机场码、新干线票价、汇率缓存）
- `config/xianyu_cookies.txt` 闲鱼 Cookie（gitignore，过期需浏览器过滑块后重拿，要带 `x5sec`）。**必须从 daemon 运行的同一台机器、同一个网络环境的浏览器拿**——cookie 里 baked 着浏览器设备指纹，跨设备/跨 IP 用会秒触风控
- `config/travelpayouts.env` Aviasales API token（gitignore）
- `xianyu/ledger.xlsx` 台账
- `logs/` 守护进程日志

## 闲鱼业务

### 报价公式

- 普通：报价 = 携程价 × 0.75 抹零；下单成本 = 携程价 × 0.4
- 利润仅在「已发回执 / 已收货」状态计入台账
- 新干线：JR 官方 JPY 价 ×1.05 markup ×汇率 → Klook 客户参考价（CNY），再 ×0.75 抹零；汇率走 `lib/fx.py` 24h 缓存

### 业务规则（硬性，违反会出错单或踩用户雷区）

- **不要手机号**。最多要邮箱
- **不做 JR Pass**。买家提到 Pass 直接说不接，不报价
- **不做酒店信用卡预授权**。要 CC guarantee 的酒店换或拒，不向买家要卡号
- **铁路（新干线）不收任何乘客身份信息**——日本铁路是匿名票，rail 类 `travelers` 数组保持空；追问只问日期、人数、起讫站、时间、席位
- **酒店只报含税价**，宿泊税含进总价，话术不要出现「不含税」「+ 税」
- **铁路买家未指定席位时，把所有可用席位并列报**（自由席 / 指定席 / 绿色车厢 / Gran Class，按线路有什么报什么）
- **廉航或需另购行李的航司**分别报「裸价」「含 23kg」两个价。命中航司：春秋、亚航、酷航、捷星、Spirit、Frontier、Ryanair、easyJet
- **日本酒店默认 15:00 入住、12:00 退房**（不是 14:00 / 11:00）
- **新干线旺季可能无自由席**（黄金周、お盆、新年；希望号 Nozomi 特定日期常年无自由席），报自由席前确认日期/班次

### 沟通话术：礼貌 + 简洁 + 沉稳

不松（"ok 就拍 / 我去下"）也不假（"您看 / 为您处理 / 方便的话"）。

✗ 避免：句尾「啦/呗/咯/嘛/哦」、「ok」、「您」（除非对方明显年长）、「为您」「方便的话」、过短动词组「我去下 / 我去出票」

✓ 倾向：完整句、动作前加「这边/我这边」、「确认/告知/需要」类稳重动词、「定了告诉我」而不是「定了喊我」

| 场景 | 错（太松） | 错（太客服） | 对 |
| --- | --- | --- | --- |
| 报价确认 tail | ok 就拍，我去下 | 请确认后下单，即刻为您处理 | 确认就拍，我这边下单 |
| 多档让买家选 | 要哪档就拍哪档 | 请您选择您所需的档位 | 确认哪档我这边下单 |
| 砍价不让 | 这价是底，搞不定 | 抱歉先生这价已是最低 | 这价是底了，做不下来 |
| 涨价告知 | 涨了，要不换个 | 非常抱歉因价格波动… | 这班涨到 ¥X，可以改 ¥X 或换 {方案 B} |
| 退款告知 | 钱退啦 | 您的款项已为您原路退还 | 款项已原路退回 |
| 催收货 | 帮忙确认下呗 | 麻烦您及时确认收货 | 行程顺利的话麻烦确认收货，谢谢 |

### 截图代回复降级流程

用户发携程/Klook/航司 app 截图让我代回买家时按四档选：

| 档 | 触发 | 命令 |
| --- | --- | --- |
| L0 全自动 | 数据齐、订单已入库 | `quote.py --order-id X --ctrip-price N --send` |
| L1 模板话术 + 我读价 | 截图给价、行程在 trip 字段里 | 同 L0，话术走模板 |
| **L2 自定义话术 + 落账（默认）** | 截图含细节（航司/时刻/转机），话术要体现 | `quote.py --order-id X --price N --quoted-text "..." --send` |
| L3 纯回复不落账 | 闲聊、答疑、订单未建 | `reply.py --chat-id X --to-uid Y --text "..." --confirm` |

操作：先 Read 截图提价格 + 航司/班次/时刻/转机；自己算 ×0.75 抹零；不确定先 dry-run（不加 --send）让用户审；拿不准 chat_id / order-id 跑 `inbox.py` 确认。

### 订单 JSON schema 关键字段

```text
xianyu_order_id, xianyu_chat_id
buyer.{nick, xianyu_uid}
item.{type=flight|hotel|rail, summary, xianyu_item_id}
trip.{origin, origin_code, destination, destination_code, is_round_trip,
      departure_date, return_date, departure_time, passenger_count,
      ticket_count, airline, route}        // route 仅 rail 用
travelers[].{name_cn, name_en, gender, passport, passport_expiry, dob, nationality, baggage}
pricing.{ctrip_price, quoted_price, currency, source}
status   询价 | 已报价 | 已付款 | 已发单 | 已出票 | 已发回执 | 已收货 | 交易关闭
timeline[].{status, at, note}
fulfillment.{supplier_pnr, supplier_attachments, buyer_receipt_sent_at}
notes[]
```

`update_status / save / load / list_all` 在 `lib/order_store.py`，状态校验和 timeline 自动追加都封装好了。

### 反风控行为

`lib/xianyu_client.send_message` 默认两条防机器人措施，所有发买家消息的命令（`reply.py` `quote.py --send` `send_receipt.py`）共享：

- **夜间静默 01:00–07:30 CST**：在静默期内 `send_message` 抛 `QuietHoursError` 拒发，避免凌晨秒回的机器人特征。需要绕过加 `--force-night`。窗口可用 env `XIANYU_QUIET_START` / `XIANYU_QUIET_END` 调（HH:MM 格式）
- **人工延迟 15–90s**：`humanize=True`（默认）时发送前 sleep `random.uniform(15,60) + len(text)*random.uniform(0.05,0.2)`，封顶 90s。`reply.py --no-delay` 跳过

### 命令（详细参数 `python commands/xxx.py -h`）

| 命令 | 用途 |
| --- | --- |
| `inbox.py [--all] [--mark-read]` | 列未处理事件，按会话分组，显示方向（← 买家 / → 你） |
| `quote.py --order-id X {--ctrip-price N \| --jpy-price N} [--ratio 0.75 \| --price N] [--markup 1.05] [--quoted-text "..."] [--send]` | 报价草稿，写 `pricing.quoted_price`，timeline 追加「已报价」 |
| `reply.py {--order-id X \| --chat-id Y --to-uid Z} --text "..." [--confirm]` | 闲鱼私信，无 `--confirm` 只 dry-run |
| `dispatch.py --order-id X [--confirm]` | 发到 TG 发单群，timeline 追加「已发单」 |
| `match_pnr.py --order-id X [--pnr CODE] [--attachment FILE]... [--pnr-file F] [--confirm]` | 关联 PNR 文本/二维码截图到订单（附件复制到 `state/attachments/orders/<id>/`），timeline 追加「已出票」 |
| `send_receipt.py --order-id X [--confirm]` | PNR 回执发买家，timeline 追加「已发回执」 |
| `mark.py {--order-id X --status S [--note N] \| --list-statuses}` | 手动推进状态（仅向前，无回滚） |
| `scripts/show_shinkansen.py FROM TO [SEAT]` | 查新干线 JR + Klook + 报价 一行（含 fuzzy 站名匹配） |
| `scripts/show_flight.py O D YYYY-MM [--return YYYY-MM] [--calendar]` | 查机票参考价（Travelpayouts/Aviasales 缓存数据，仅作对照携程参考） |
| `scripts/show_airport.py {IATA \| 城市}` | 查机场三字码、同城多机场 |
| `scripts/show_fx.py [--refresh] [--jpy N]` | 查 / 刷新 JPY→CNY 汇率 |
| `scripts/update_xianyu_ledger.py` | 刷新 `xianyu/ledger.xlsx`（10 列：出发日 / 行程 / 人 / 买家 / 成交价 / 携程价 / 利润 / 状态 / PNR / 备注；二维码附件作超链接） |

### 启动守护进程

```bash
nohup .venv/bin/python daemons/xianyu_daemon.py > logs/xianyu_daemon.log 2>&1 &
```

Cookie 过期日志会出 `RGV587_ERROR` / `被挤爆啦`。

### 闲鱼商品文案风格

真实、口语化，不堆砌形容词。说清楚品相、原价、出价理由。

## 视频处理默认参数

输出 mp4（H.264 + AAC），分辨率保持原始；脚本接收输入路径作为参数，输出到同目录 `{原文件名}_out.mp4`。
