---
description: 给钦钦推荐绘本(按当前月龄 + 权威书单,带源)
allowed-tools: Read, WebSearch, WebFetch, Edit, Bash
---

# 任务

给钦钦推荐绘本,**严禁凭印象编书名 / 编出版社**。

## 步骤

1. 读 `parenting/profile.json` 拿出生日期 → 算当前月龄。
2. 解析用户输入 `$ARGUMENTS`(可能为空,或包含: 主题如「情绪 / 数数 / 睡前」、语言 zh/en、数量 N)。
3. 按当前月龄从下面**白名单源**里拉 3-5 本推荐。多源交叉,不依赖单一渠道:
   - **ALSC Notable Children's Books**(younger readers)https://www.ala.org/alsc/awardsgrants/notalists/ncb
   - **Caldecott Medal & Honor Books**(美国童书最高奖)https://www.ala.org/alsc/awardsgrants/bookmedia/caldecott
   - **AAP Reach Out and Read 推荐**(儿科医生发的书目)https://reachoutandread.org/
   - **BookTrust BookStart**(英国 0-5 岁阅读基金会)https://www.booktrust.org.uk/books-and-reading/bookfinder/
   - 中文: **信谊图画书奖**(3-8 岁起步)、**丰子恺儿童图画书奖**、**中国新闻出版广电局推优童书**、**国图少儿馆推荐**
4. 每本输出:
   - 标题 / 作者 / 译者(中文版)/ 出版社 / 适龄
   - 一句话推荐理由(钦钦能从中获得什么)
   - **来源 URL**(必填,缺源不推)
5. 推荐完成后**问用户**: 想加入哪几本到 `parenting/library/books.json`?
6. 用户确认后,Edit 该 JSON,每本带完整字段 + `source` URL + `retrieved` 日期 + `status: wishlist`。

## 红线

- 没有源链就不给。你不知道的书直接说「这条暂无权威源,不推」。
- 不要堆砌「经典必读」类水分话术,每本都说为什么适合**钦钦此刻**。
- 中文版书名要核对译本(同一本英文绘本中文译名可能差异大,如 Where the Wild Things Are = 野兽国 / 野兽出没的地方)。
