# 股票新闻分析

## 模块定位

股票新闻分析是股票板块里的平行通道，用来承载新闻、事件、公告、独家报道、管理层表述、分析师预期和非行情类数据播报等客观信息。

它和股票观点分析并行存在，但不替代观点链路：

- `viewpoints` 只代表作者本人方向性判断。
- `events` 只代表客观事件，不推导作者立场。

股票板块提供两个新闻页面：

- `/stocks/news`：按日期展示新闻时间线。
- `/stocks/news/tracking`：展示管理员选择追踪的新闻，以及 AI 映射出来的受益股票和入选后涨幅。

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

`event_type` 新增 `supply_risk`，专门承载短缺、断供、供应无法保障、关键材料涨价、供应商产能受限或建议客户多元采购等供应风险新闻。它不同于普通 `supply_chain_update`，前端会优先展示并高亮。

纯股票、指数、ETF 或市场价格上涨/下跌、盘前盘后涨跌、创高创低等行情涨跌播报不进入 `events`，也不算股票新闻。材料、零部件或服务本身的涨价仍可作为 `supply_risk`。

`events` 必须是近期具体发生或披露的事情。历史研究报告分享、长期规律回顾、行业知识科普、技术概念解释、工业流程定义、产品/工艺关系辨析不进入 `events`；这类内容即使客观，也不是新闻事件。

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
| `stock_news_tracking` | 管理员选择追踪的新闻事件，按 `event_key` 去重。 |
| `stock_news_tracking_stocks` | 单条追踪新闻映射出的受益股票、逻辑和价格表现。 |

事件对象与观点对象分开存储，不复用 `content_viewpoints`。

`stock_news_daily_timeline.events_json` 中每条事件都带 `event_key` 和
`event_sort_order`。`event_key` 由 `note_id + event_sort_order + headline`
生成，用作追踪去重和 AI 一次性分析的稳定锚点。

## 页面口径

`/stocks/news` 以日期为第一轴：

- 按日期倒序展示。
- 每个日期块显示当天全部新闻详情。
- 单条新闻压缩展示为紧凑时间线行，聚合作者、发布时间、原文链接、事件标签和关联实体 badge。
- `supply_risk` 事件在同一日期内优先排序，并使用警示样式突出显示。
- 前端支持“只看供应风险”筛选，只保留 `event_type = supply_risk` 的事件和仍有事件的日期分组。
- 正文只保留标题和事件摘要，不单独展示依据字段。

管理员在 `/stocks/news` 可以选择单条新闻追踪。追踪结果全站共享，普通用户只读。
后台每小时扫描待分析新闻，使用 `gpt-5.4` 和 `reasoning_effort=high`
对每条新闻只分析一次，最多保留 30 只映射股票；管理员可在
`/stocks/news/tracking` 删除整条追踪新闻、批量删除多条追踪新闻，或删除单条新闻下不匹配的映射股票。每天北京时间 08:00
和 20:00 刷新映射股票行情，涨幅基准为 AI 入选日的可用交易日收盘价。

追踪分析使用一跳产业链口径。AI 必须先识别新闻核心商品、材料、工艺、
零部件、设备或服务，然后只允许输出 `self`、`peer`、`upstream_1` 和
`downstream_1` 四类股票：本身/同环节替代、直接上游和直接下游。不能继续
推演到二阶或三阶主题，例如从 InP 推到光模块、AI 数据中心或电信投资，也
不能用泛化的本土替代、产业景气或估值弹性列入股票。服务端会丢弃未标注为
这四类一跳层级的 AI 输出。

仍然不进入：

- 不进入作者时间线。
- 不进入单只股票详情页。
- 不进入观点矩阵、点金榜、叙事简报和顶部风险。
- 新闻页关联实体 badge 只展示，不提供跳转。
