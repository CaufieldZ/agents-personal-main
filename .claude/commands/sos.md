---
description: 描述钦钦的症状/突发情况,给基于权威指南的初步应对建议(非医疗诊断)
allowed-tools: Read, WebSearch, WebFetch, Write, Bash
---

# 任务

用户传入症状描述 `$ARGUMENTS`(如「39 度发烧 6 小时,精神还行」、「前额磕了个包」、「拉肚子第三天」、「呛奶后呼吸不顺」)。

你**不是医生**。你做的是: 把症状对照权威儿科指南,给三档分诊 + 居家观察清单 + 就医信号。

## 步骤

1. 读 `parenting/profile.json`(月龄、过敏、慢性病)+ `parenting/schedule/medications.json`(在用药)+ `parenting/schedule/vaccines.json`(近期接种,接种 48h 内的反应另判)。
2. 解析症状关键词,从**白名单源**拉对应主题指南:
   - **AAP HealthyChildren Symptom Checker**
     https://www.healthychildren.org/English/health-issues/conditions/
   - **AAP Pediatric Care Online**(若可访问)
   - **NHS — Children's health A to Z** https://www.nhs.uk/conditions/baby/
   - **WHO IMCI**(发展中国家儿童病例管理)https://www.who.int/teams/maternal-newborn-child-adolescent-health-and-ageing/child-health/integrated-management-of-childhood-illness
   - **中国国家卫生健康委儿童常见病诊疗规范**(可信源)
   - **Seattle Children's Symptom Decision Tool**(AAP 体系常用) https://www.seattlechildrens.org/conditions/a-z/
3. 输出**严格三档**:

   ### 立刻 120 / 急诊
   红旗信号(对当前症状的具体表现),如:
   - 呼吸: 鼻翼煽动 / 三凹征 / 嘴唇紫绀 / 呼吸 >60 次/分(婴幼儿)
   - 神志: 叫不醒 / 抽搐 / 持续哭闹无法安抚 / 极度嗜睡
   - 出血: 喷射性 / 大面积 / 止不住 >10 分钟
   - 其他: 高热惊厥首发 / <3 月龄 ≥38°C / 频繁呕吐无尿 / 头部伤后呕吐意识改变

   ### 24 小时内门诊 / 儿童医院夜诊
   ……(列具体触发条件)

   ### 居家观察 + 何时升级
   - 现在能做什么(具体到剂量,如对乙酰氨基酚 10-15 mg/kg/次,间隔不少于 4-6 小时,24h 不超过 5 次)
   - 监控指标 + 频率(每 X 小时测 Y)
   - 升级到上一档的明确时机

4. 末尾**强制写入**:
   ```
   --- 重要 ---
   这是基于公开权威儿科指南的初步参考,不替代医生判断。
   任何不放心 → 打 120 或去儿童医院急诊。
   杭州儿童急诊参考: 浙大儿院滨江/湖滨院区 24h 急诊。
   ```

5. 把这次对话存档到 `parenting/notes/sos/{YYYY-MM-DD-HHMM}-{关键词}.md`,包含: 症状原话、月龄、给出的建议、引用源 URL。这样以后回看病史能查。

## 红线

- 不下诊断结论。不写「这是手足口」「这是肺炎」,只能写「符合 X 描述,建议查 X」。
- 不推荐处方药(抗生素 / 激素)。OTC 退烧 / 补液盐可以引指南剂量,但必须按月龄 / 体重计算,并提示「按说明书 + 接种证里医生开过的药为准」。
- 引用的源必须真实存在且当下能访问。WebFetch 失败的源不要列出来。
- 钦钦过敏 / 慢性病 / 在用药的内容如果与症状相关,顶部红字标出。
