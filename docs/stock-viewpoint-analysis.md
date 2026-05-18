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
- `叙事简报`
- `顶部风险`
- `管理`

现阶段股票板块的产品含义如下：

| 页面 | 路由 | 用途 |
| --- | --- | --- |
| 总览 | `/` | 展示账号数、订阅数和最近更新预览。 |
| 账号库 | `/accounts` | 浏览已审批 X 账号，登录后可订阅或提交新账号。 |
| 我的订阅 | `/feed` | 按账号查看订阅作者的观点时间线。 |
| 按股票（详情） | `/stocks` | 按单只股票查看 K 线、日线观点标记和作者观点。 |
| 按股票（一览表） | `/stocks/overview` | 查看股票 x 作者观点矩阵，支持按周或按日切换，并自动隐藏当前窗口里完全空白的行列。 |
| 叙事简报 | `/stocks/narrative` | 展示全站可见的主流叙事、新风向和少见负面声音。 |
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

`/stocks/overview` 通过 `get_visible_stock_matrix` 获取股票 x 作者矩阵。默认按周展示，以当前用户可见范围里的最新 `date_key` 作为结束日，窗口覆盖最近 7 个自然日；切到按日后，窗口只显示单个自然日。同一作者在当前窗口内多次提及同一股票时，每条有效观点都作为独立红/绿点返回，不合并为单个观点。当前窗口里完全没有观点的作者列和股票行不会渲染。

## 股票叙事简报

股票叙事简报位于 `/stocks/narrative`，左侧导航显示为 `叙事简报`，位置在 `顶部风险` 上方。简报基于所有管理员已审批的股票账号生成，全站可见，不按个人订阅范围过滤。

目标是把近期作者观点压成一篇偏中立的小作文，重点回答三件事：

- 主流叙事：多名作者近期都在认可的逻辑、主题、产业链或股票题材。
- 新风向：过去窗口里很少出现，但最近开始被作者提到或明显升温的话题。
- 少见负面声音：样本里不占主流、但和主流叙事相反或提示风险的观点。

### 输入口径

生成时以当前所有已审批股票账号里的最新 `date_key` 为结束点，向前取最近 7 个有股票观点数据的日期。产品文案可以写成“近 7 个交易/有效观点日”；如果后续需要严格按美股、A 股或港股交易日切分，再单独接入交易所日历。

输入给叙事 AI 的单条观点只保留最小必要信息：

| 字段 | 用途 |
| --- | --- |
| 作者 | 使用 `account_name` 展示名；不使用平台昵称作为主名。 |
| 时间 | 使用观点对应的 `date_key` 或原内容 `publish_time`。 |
| 方向 | 使用 `direction` 的正向/负向短标记，便于发现少见负面声音。 |
| 逻辑 | 使用已有 AI 生成的 `logic`。 |
| 证据 | 使用已有 AI 生成的 `evidence`。 |

不要把单条观点的独立 `entity_name`、`entity_key`、ticker 或“AI 生成对象”作为单独输入字段传给叙事 AI，避免简报退化成股票列表。但 `logic` 和 `evidence` 里自然出现的公司名、产品线、行业词不应二次删除，否则 AI 会失去归纳题材和产业链的线索。

每次生成时会附上上一条成功简报作为连续性输入，并优先读取上一段非重叠 7 日窗口简报作为新旧对照。连续性输入只用于提醒 AI “上一期已经怎么概括过”，不能作为判断新题材的唯一历史基线。

### 7 日窗口与新风向判断

不建议把过去 30 天的所有 `logic`、`evidence` 原文一次性塞给 AI。这样 token 浪费明显，而且旧观点会稀释最近几天的变化。

采用“7 日高保真输入 + 14/30 日低成本基线”的两层口径：

- 当前窗口：最近 7 个交易/有效观点日的逐条观点，保留作者、时间、方向、逻辑和证据。
- 历史基线：保留过去 14 和 30 个自然日的主题指纹，而不是完整原文。
- 连续性基线：附上上一周期小作文，帮助 AI 不重复写昨天已经稳定存在的主流叙事。

历史基线可以是由程序或上一轮 AI 维护的结构化摘要，例如：

| 字段 | 含义 |
| --- | --- |
| `topic` | 主题短语，如“AI 算力链”“稳定币相关股票”“核电电力需求”。 |
| `first_seen_date` | 最近基线里首次出现日期。 |
| `recent_7d_count` | 当前 7 日窗口命中次数。 |
| `baseline_count` | 历史基线窗口命中次数。 |
| `author_count` | 提到该主题的作者数量。 |
| `sample_evidence` | 最多 1 到 2 条短证据，不放完整原文。 |

“新风向”不应只等同于“昨天小作文没有写”。推荐分三类输出：

- 新出现：历史基线里没有，当前窗口出现，并且至少有明确证据支撑。
- 明显升温：历史基线里有零星出现，但当前窗口作者数或命中次数明显上升。
- 单点早期信号：只有一个作者提到，不能写成市场共识，只能标注为早期提法。

单纯依赖小作文之间的对比会比较省 token，但有两个问题：小作文会丢掉低频主题，且上一轮 AI 的遗漏会在后续周期里继续放大。因此上一周期小作文适合作为“叙事连续性输入”，不适合作为唯一的新题材检测来源。

### 输出口径

叙事 AI 输出一篇中文短文，语气偏中立，不给买卖指令。建议结构固定但文字自然：

- 先写主流叙事：哪些逻辑被多名作者反复认可，认可集中在哪些题材或股票类型。
- 再写新风向：哪些话题最近开始被提到，区分“新出现”“明显升温”和“单点早期信号”。
- 最后写少见负面声音：样本里有哪些反向观点或风险提示，说明它们目前是少数声音还是正在增多。

输出应避免：

- 把单个作者的一条观点写成“大家都认为”。
- 为没有证据的主题补行业背景。
- 生成新的股票推荐、目标价或交易建议。
- 只罗列 ticker，而不解释背后的共同逻辑。

如果样本量不足，应直接说明“本周期样本不足以判断主流叙事或新风向”，不要硬写结论。

### 存储和权限边界

简报第一版明确为全站可见，输入来自全部 `stock` domain 下管理员已审批账号。它不是个人订阅视图，因此可以让未登录用户读取最新简报。

`stock_narrative_briefs` 保存每次生成结果，主要字段包括：

| 字段 | 含义 |
| --- | --- |
| `brief_date` | 简报日期。 |
| `window_start` / `window_end` | 当前观点窗口。 |
| `previous_window_start` / `previous_window_end` | 上一非重叠观点窗口。 |
| `baseline_start` / `baseline_end` | 30 日主题基线窗口。 |
| `input_digest_json` | 7 日输入摘要和历史主题基线，不存密钥或外部 token。 |
| `brief_sections_json` | `主流叙事`、`新风向`、`少见负面声音` 的结构化句子。 |
| `brief_text` | 最终中文小作文。 |
| `status` / `error_text` | 生成状态和错误说明。 |
| `model_name` / `prompt_version` / `usage_json` | 生成模型、prompt 版本和 token 使用。 |
| `created_at` | 生成时间。 |

公开端通过 `get_latest_stock_narrative_brief()` 读取最新 `succeeded` 简报。后端命令为：

| 命令 | 作用 |
| --- | --- |
| `python backend/src/main.py public-generate-stock-narrative` | 基于最新可用股票观点日生成简报。 |
| `python backend/src/main.py public-generate-stock-narrative --date YYYY-MM-DD --force` | 强制重生成指定日期简报。 |

`public-worker` 会按 `PUBLIC_WORKER_STOCK_NARRATIVE_TIME` 每日自动生成，默认 `22:40`（Asia/Shanghai）。

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
