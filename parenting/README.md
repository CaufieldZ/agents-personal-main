# 育儿助手 / 钦钦专属

支怀瑾(钦钦),女,2025-03-25 出生,杭州临平。

## 目录

```text
parenting/
├── profile.json              孩子档案 + 监护人(.gitignore)
├── schedule/                 (.gitignore)
│   ├── vaccines.json         疫苗:已完成 19 针 + 未来计划,源 NIP 2021
│   ├── checkups.json         儿保体检节点
│   └── medications.json      用药记录(空)
├── library/
│   ├── books.json            绘本(空,新加项必须带 source)
│   ├── songs.json            童谣(空)
│   └── recipes/              食谱单文件 md,见 README
└── notes/                    (.gitignore)
    ├── sleep.md              睡眠时长(AAP/AASM + WHO)
    ├── screen_time.md        屏幕时间(AAP + WHO)
    ├── physical_activity.md  身体活动 / 久坐(WHO)
    ├── feeding_toddler.md    1-2 岁喂养(AAP + WHO)
    ├── milestones.md         15/18 月发展里程碑(CDC 2022)
    └── ebff210580cb...pdf    浙江省电子预防接种证(原始 PDF)
```

## 命令

### Slash 命令(Claude 跑)

| 命令 | 用途 |
| --- | --- |
| `/book [主题/语言/数量]` | 按月龄从 ALSC / Caldecott / ROR / 信谊等白名单源拉绘本推荐,确认后追加到 `library/books.json` |
| `/toy [类别/预算]` | 按 CDC milestone 推玩具类型,带安全要点(GB 6675 / CPSC),追加到 `library/toys.json` |
| `/sos {症状描述}` | 描述钦钦症状,给三档分诊(120 / 24h 内门诊 / 居家观察)+ 引用 AAP/NHS 指南,存档到 `notes/sos/{时间}-{关键词}.md` |

定义在 [.claude/commands/](../.claude/commands/),可直接编辑。

### 脚本命令

```bash
# 看未来 90 天该打的疫苗 / 体检
.venv/bin/python commands/parenting/upcoming.py
.venv/bin/python commands/parenting/upcoming.py --days 365
.venv/bin/python commands/parenting/upcoming.py --all

# 查素材库
.venv/bin/python commands/parenting/lib.py books
.venv/bin/python commands/parenting/lib.py books --status owned
.venv/bin/python commands/parenting/lib.py songs --language zh
.venv/bin/python commands/parenting/lib.py recipes
```

## 内容来源原则

所有 notes 顶部必须有 `sources:` 列表 + `retrieved:` 日期。

权威源白名单(优先级从高到低):

- **疫苗**: 国家卫健委 nhc.gov.cn / 中国疾控 chinacdc.cn
- **发展里程碑**: CDC Learn the Signs Act Early (cdc.gov/act-early)
- **睡眠 / 屏幕 / 喂养 / 行为**: AAP HealthyChildren.org + WHO who.int
- **绘本书单**: 国图儿童阅读推广委员会、ALSC Notable Books、AAP Reach Out and Read

不在白名单的内容(自媒体、母婴 KOL、商品页)不进 notes,可放 wishlist 但要标 `source: 待核实`。

## 接种历史快速核对

钦钦走的非标准路径:

- **巴斯德 DTaP-IPV/Hib 五联** 替代 IPV(4 剂) + DTaP 前 3 剂 + Hib(4 剂)。已打 3 剂,**18 月加强** 2026-09-25 前后必须打。
- **乙脑灭活路线** (8 月 ×2 + 2 岁 + 6 岁,共 4 剂)。已打 2 剂,2 岁第 3 剂。
- **ACYW 流脑结合**(康希诺)替代 NIP 的 MPSV-A 前 2 剂,但 NIP 仍要求 3 岁打 MPSV-AC。
- **甲肝**未开始,18 月起。需选灭活(2 剂)还是减毒(1 剂)。

详细: `schedule/vaccines.json`。
