# 股票观点分析方案

## 模块定位

股票观点分析负责把已抓取内容转成可浏览的股票投研观点，并按作者、股票和日期生成聚合视图。

本模块不负责：

- 抓取 X 或小红书内容。
- 维护账号审批、订阅和登录权限。
- 计算美股顶部风险预判。
- 分析 crypto、宏观、Theme、行业或板块观点。

当前公开产品是股票信号优先的形态。AI 抽取、归一化、聚合、前端股票视图和行情 K 线都围绕股票标的设计。

## 当前页面结构

公开端位于 `public-web`，当前左侧导航包含：

- `总览`
- `账号库`
- `我的订阅`
- `按股票（详情）`
- `按股票（一览表）`
- `顶部风险`
- `管理`

现阶段股票板块的产品含义如下：

| 页面 | 路由 | 用途 |
| --- | --- | --- |
| 总览 | `/` | 展示账号数、订阅数和最近更新预览。 |
| 账号库 | `/accounts` | 浏览已审批 X 账号，登录后可订阅或提交新账号。 |
| 我的订阅 | `/feed` | 按账号查看订阅作者的观点时间线。 |
| 按股票（详情） | `/stocks` | 按单只股票查看 K 线、日线观点标记和作者观点。 |
| 按股票（一览表） | `/stocks/overview` | 查看最近 7 个有数据自然日的股票 x 作者观点矩阵。 |
| 顶部风险 | `/risk` | 展示美股顶部风险状态，不给个股买卖指令。 |
| 管理 | `/admin` | 管理员处理账号请求和任务，只对管理员邮箱显示。 |

后续新增 crypto 或其他板块时，建议在左侧品牌区下方、功能导航上方加入静态板块切换，不使用 hover 展开。股票板块内的页面主体布局可以保持不变，只把股票相关文案逐步泛化为“标的”。

## 输入来源

分析模块读取已经入库的统一内容记录，主要来自：

- X 账号抓取模块。
- 历史小红书抓取模块。

统一内容模型为 `RawNoteRecord`，入库表为 `content_items`。关键字段包括：

| 字段 | 含义 |
| --- | --- |
| `platform` | 来源平台，如 `x` 或 `xhs`。 |
| `account_name` | 本地账号名。 |
| `external_content_id` | 平台内容 ID。 |
| `url` | 原始内容链接。 |
| `title` | 标题或正文摘要。 |
| `body_text` | 正文。 |
| `publish_time` | 发布时间。 |
| `fetched_at` | 抓取时间。 |

分析模块只处理已入库内容，不直接访问外部平台。

## AI 配置

AI 配置优先级：

1. `data/config/ai_settings.local.json`
2. 根目录 `.env`
3. 代码默认值

旧本地控制台 `/control` 保存的配置会写入 `data/config/ai_settings.local.json`。API key 输入框留空保存表示保留旧 key，不会回显已保存 key。

## Prompt 口径

当前 prompt 定义在 `backend/packages/ai/prompts.py`。

单条内容抽取使用 `build_note_extract_messages`，核心口径是：

- 输出必须是 JSON 对象，不输出 markdown。
- 顶层字段必须包含 `summary_text` 和 `viewpoints`。
- `summary_text` 是一句中文概括，说明该内容里的有效股票观点；没有有效股票观点时写“未形成有效股票观点”。
- `viewpoints` 是独立股票观点数组；没有有效股票观点时返回空数组。
- `entity_type` 当前只允许 `stock`。
- 非股票、Theme、行业、板块、赛道、宏观、指数、市场风格、纯新闻和其他对象都忽略。
- 股票字段必须规范化：`entity_name` 写公司或证券名称，`entity_code_or_name` 写 ticker 或股票代码。
- 美股 ticker 使用普通代码，例如 `NVDA`、`AMD`、`INTC`；A 股和台股可以保留市场后缀或原始代码。

有效观点必须满足：

| 字段 | 要求 |
| --- | --- |
| `entity_type` | 当前只保留 `stock`。 |
| `direction` | 必须是 `positive` 或 `negative`。 |
| `signal_type` | 必须是 `explicit_stance` 或 `logic_based`。 |
| `judgment_type` | 不能是 `factual_only`、`quoted`、`mention_only`。 |
| `conviction` | `strong`、`medium`、`weak`、`none` 或 `unknown`。 |
| `evidence_type` | 财报、指引、管理层信号、估值、政策、传闻、持仓、资金流、技术、宏观等证据类型。 |
| `time_horizon` | `short_term`、`medium_term`、`long_term` 或 `unspecified`。 |

过滤原则：

- 只提及股票但没有方向性判断，不输出。
- 纯行情、财报、新闻、列表、转述他人观点，不输出。
- 作者转述公司管理层或机构信息，但明确表达自己因此继续持有、看好、买入、卖出或避开，可以输出。
- 供应链、产品线、业务部门只有在作者明确转成上市公司股票结论时才输出。
- 同一对象只有一个判断时，只输出一条，不拆碎。

日总结使用 `build_author_day_summary_messages`，基于同一作者某一天的多篇结构化结果生成一句时间线标题，突出当天最核心的股票方向。

## 分析流程

1. 读取已入库内容。
2. 根据 `analysis_version` 判断哪些内容需要补分析或重分析。
3. 对每条待处理内容调用 AI，生成 JSON。
4. 校验 JSON 必需字段。
5. 解析结构化观点为 `ViewpointRecord`。
6. 用 `security_aliases.json` 归一化股票名称、ticker 和市场。
7. 写入 `content_analyses` 和 `content_viewpoints`。
8. 按作者、日期聚合为 `author_daily_summaries`。
9. 按股票、日期聚合为 `security_daily_views`。
10. 轻量刷新相关股票近期行情，写入 `security_daily_prices`。
11. 生成本地 snapshot，写入 `data/runtime/ai/snapshots/`。

公开 Supabase worker 的分析重建窗口默认是 30 个上海自然日，和初始回填的 30 天内容窗口一致。定时抓取可以只抓较少新帖，但清空并重建分析表时不能只用 1 到 3 天窗口，否则作者时间线会被重建成只剩最近几天。

## 股票归一化

股票别名配置位于 `data/config/security_aliases.json`，示例文件为 `data/config/security_aliases.example.json`。

归一化目标：

- 同一股票的中文名、英文名、ticker、别名映射到同一个 `security_key`。
- 页面展示使用配置中的 `display_name`。
- 没有可靠映射的观点不进入核心股票视图。

归一化发生在解析和重建阶段。`content_viewpoints`、`security_entities`、`security_daily_views` 和前端 RPC 都依赖同一套 `security_key`。

## 聚合结果

| 表 | 用途 |
| --- | --- |
| `content_analyses` | 单条内容的 AI 摘要和原始响应。 |
| `content_viewpoints` | 单条内容拆出的结构化观点。 |
| `security_entities` | 股票实体、ticker、市场和展示名。 |
| `security_mentions` | 兼容旧结构的股票提及记录。 |
| `author_daily_summaries` | 作者每天的观点摘要。 |
| `security_daily_views` | 股票每天被哪些作者如何看待。 |
| `security_daily_prices` | 股票日线价格缓存，公开 K 线按 180 天窗口读取。 |
| `analysis_runs` | 每次分析运行记录。 |

当前股票聚合是 stock-signal-only 口径。`theme_daily_views` 不承载公开产品数据。

## 前端数据口径

`/feed` 通过作者维度展示观点时间线。登录用户只看到自己订阅范围；未登录用户只看到公开轻量预览范围。

`/stocks` 通过 `list_visible_entities` 获取可见股票列表，通过 `get_visible_entity_timeline` 获取单只股票详情。详情页支持：

- 快速切换股票。
- 按最近日期或累计提及排序。
- 展示股票身份标签。
- 登录后展示 K 线和观点标记。
- 展示按日聚合的作者观点、逻辑、证据和原文链接。

`/stocks/overview` 通过 `get_visible_stock_matrix` 获取最近 7 个有数据自然日的矩阵。默认结束日是当前用户可见范围里的最新 `date_key`。同一作者在窗口内多次提及同一股票时，每条有效观点都作为独立红/绿点返回，不合并为单个观点。

## 行情和 K 线

股票行情由分析流程的轻量刷新或单独刷新命令写入 `security_daily_prices`。

约束：

- 轻量刷新只控制本次抓取最近几天的数据，不裁剪已有日线缓存。
- 公开 K 线读取仍保留 180 天缓存窗口。
- 没有行情数据时，股票详情仍应展示观点时间线。
- 当前行情逻辑服务股票，不作为 crypto 第一版的必需能力。

## 顶部风险边界

顶部风险是独立模块，公开页面为 `/risk`，文档见 `docs/us-market-top-risk.md`。

它和股票观点分析的关系是：

- 同在股票板块展示。
- 不参与单条内容观点抽取。
- 不改变股票观点方向。
- 不给买卖指令。

后续 crypto 板块不应直接复用现有顶部风险，除非另行设计 crypto 风险指标和文档。

## 重跑语义

| 命令 | 作用 |
| --- | --- |
| `python backend/src/main.py run-once --config data/config/watchlist.json` | 小红书抓取后分析。 |
| `python backend/src/main.py run-once-x --config data/config/x_watchlist.json` | X 抓取后分析。 |
| `python backend/src/main.py reanalyze-existing` | 对现有内容强制重新生成 AI 观点。 |
| `python backend/src/main.py normalize-securities` | 根据别名配置重新归一化并重建视图。 |
| `python backend/src/main.py public-refresh-market-data` | 刷新公开 Supabase 股票行情缓存。 |
| `python backend/src/main.py public-normalize-securities` | 归一化公开 Supabase 股票身份、重建时间线并刷新行情。 |

## 设计约束

- 股票观点只保留有方向、有逻辑或明确态度的内容。
- AI 输出必须经过结构校验、观点过滤和股票归一化。
- 聚合视图可重建，不能依赖一次性不可复现状态。
- 前端可见范围必须尊重登录和订阅权限。
- API key、数据库 URL、本地 snapshot 和运行时缓存不提交 Git。
- crypto 或其他新板块应使用独立 prompt 版本、独立产品文档和清晰的实体归一化规则。
