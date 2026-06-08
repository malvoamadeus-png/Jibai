# 股票新闻分析

## 模块定位

股票新闻分析是股票板块里的平行通道，用来承载新闻、事件、公告、独家报道、管理层表述、分析师预期和数据播报等客观信息。

它和股票观点分析并行存在，但不替代观点链路：

- `viewpoints` 只代表作者本人方向性判断。
- `events` 只代表客观事件，不推导作者立场。

第一版只在股票板块提供独立页面 `/stocks/news`，按日期展示新闻时间线。

## 抽取口径

单条内容的股票抽取现在同时输出：

- `summary_text`
- `viewpoints`
- `events`

`events` 的最小字段：

| 字段 | 含义 |
| --- | --- |
| `headline` | 事件短标题。 |
| `event_summary` | 1 到 2 句中文说明发生了什么。 |
| `event_type` | 事件类型，如 `earnings_update`、`policy_update`、`profitability_outlook`。 |
| `event_nature` | 事件性质，如 `reported`、`announced`、`exclusive`、`expected`。 |
| `linked_entities` | 该事件关联的对象列表。 |

当前 `linked_entities` 只允许两类：

- `stock`
- `theme`

如果作者既在报道事件，又明确表达自己的买卖方向，应同时输出 `event` 和 `viewpoint`。

## 存储结构

| 表 | 用途 |
| --- | --- |
| `content_events` | 单条内容拆出的事件原子项。 |
| `content_event_entities` | 事件和股票/主题实体的关联。 |
| `stock_news_daily_timeline` | 股票新闻按日期聚合后的时间线。 |

事件对象与观点对象分开存储，不复用 `content_viewpoints`。

## 页面口径

`/stocks/news` 以日期为第一轴：

- 按日期倒序展示。
- 每个日期块显示当天全部新闻详情。
- 单条新闻压缩展示为紧凑时间线行，聚合作者、发布时间、原文链接、事件标签和关联实体 badge。
- 正文只保留标题和事件摘要，不单独展示依据字段。

第一版限制：

- 不进入作者时间线。
- 不进入单只股票详情页。
- 不进入观点矩阵、点金榜、叙事简报和顶部风险。
- 关联实体 badge 只展示，不提供跳转。
