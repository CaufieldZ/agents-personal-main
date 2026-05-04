---
description: 给钦钦推荐玩具(按发展里程碑 + 安全标准,带源)
allowed-tools: Read, WebSearch, WebFetch, Edit, Write, Bash
---

# 任务

给钦钦推荐玩具,**先安全,再发展适配**。不推某品牌网红款,推**功能类型**(让用户自选品牌)。

## 步骤

1. 读 `parenting/profile.json` 拿月龄,读 `parenting/notes/milestones.md` 拿当前 / 下一阶段 milestones。
2. 解析 `$ARGUMENTS`(可空,或: 类别如「精细动作 / 大运动 / 语言 / 假装游戏」、预算)。
3. 按月龄从下面**白名单源**找推荐:
   - **AAP HealthyChildren — Selecting Appropriate Toys for Young Children**
     https://www.healthychildren.org/English/family-life/Media/Pages/Selecting-Appropriate-Toys-for-Young-Children-Media-Age.aspx
   - **AAP Clinical Report: Selecting Appropriate Toys for Young Children in the Digital Era**(Pediatrics)
     https://publications.aap.org/pediatrics/article/142/6/e20183348/37618/
   - **CDC Learn the Signs Act Early — Activities for 12/15/18 Months**
     https://www.cdc.gov/act-early/milestones-in-action/index.html
   - **Common Sense Media — Toys**(评测)https://www.commonsensemedia.org/lists
   - **U.S. CPSC Toy Safety**(消费品安全委员会)https://www.cpsc.gov/Safety-Education/Safety-Education-Centers/Toys
   - 中国: **GB 6675 玩具安全国家标准**(查 3C 认证)
4. 输出每条:
   - 玩具**类型**(如「形状嵌板」「推拉学步车」「软质布书」)
   - 锚定的 milestone(具体哪条 CDC 里程碑)
   - 安全要点(<3 岁: 无小于 3.17 cm 的可拆零件 / 无磁力珠 / 无含铅涂料 / 选 3C 认证)
   - 备选具体款(可选 1-2 个具体型号,但必须从源页里出现过的)
   - 来源 URL
5. 推荐完后**问用户**: 加哪些到 `parenting/library/toys.json` wishlist? 已有的标 owned。
6. 用户确认后写入 JSON,带 `source` + `retrieved`。

## 红线

- 不推: 含小磁珠 / 钮扣电池暴露 / 长绳带(>22 cm)/ 弹射玩具(<3 岁) / 未标 3C 或 CE 的电子玩具。
- 不推屏幕类电子玩具(冲突 `notes/screen_time.md`)。
- 安全话题严格,推荐过的玩具宁缺毋滥。
