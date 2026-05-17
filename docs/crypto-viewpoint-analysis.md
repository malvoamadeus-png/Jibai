# Crypto 观点分析方案

## 文档状态

本文记录当前 crypto 板块第一版实现口径。股票观点分析见 [股票观点分析方案](stock-viewpoint-analysis.md)。crypto 板块作为独立资产类别接入，不复用股票 prompt、股票归一化规则、股票 K 线和美股顶部风险。

## 模块定位

Crypto 观点分析负责追踪 crypto domain 下已审批的 X 账号，抽取其对加密代币或加密项目的方向性观点和弱信息信号，并按作者、标的和日期生成可浏览的聚合视图。

第一版目标：

- 继续沿用“追踪已审批 X 账号 -> 抓取内容 -> AI 抽取观点 -> 聚合展示”的主链路。
- 抽取作者本人对 crypto 标的的正向或负向判断。
- 保留单纯转发、提及、公告、数据播报或价格播报作为弱信号。
- 按作者查看订阅账号的 crypto 观点时间线。
- 按标的查看单个 crypto 标的的观点详情。
- 按标的一览表查看近期 crypto 标的 x 作者矩阵。
- 管理入口仍只对管理员邮箱显示。

第一版不做：

- 不接 K 线图。
- 不做 crypto 顶部风险。
- 不做链上实时监控、钱包追踪或交易执行。
- 不把空投教程、交互教程、白名单、邀请码等操作流程纳入核心观点。
- 不把股票、crypto-stock、矿企或交易所股票混入 crypto 标的视图；这类内容仍归股票板块。

## 产品导航

当前前端在左侧 sidebar 的品牌区下方、功能导航上方加入静态板块切换：

- `股票`
- `加密`
- 导航结构保留继续添加 `宏观`、`链上`、`组合` 等板块的空间

不使用 hover 展开。静态板块切换更适合移动端，可发现性更好，性能开销也低。

Crypto 板块第一版页面：

| 页面 | 路由 | 用途 |
| --- | --- | --- |
| 总览 | `/crypto` | 展示 crypto 板块的账号数、订阅数和最近更新预览。 |
| 账号库 | `/crypto/accounts` | 浏览 crypto 板块已审批 X 账号，登录后可订阅或提交新账号。 |
| 我的订阅 | `/crypto/feed` | 按账号查看订阅作者的 crypto 观点时间线。 |
| 按标的（详情） | `/crypto/assets` | 按单个 crypto 标的查看按日作者观点。 |
| 按标的（一览表） | `/crypto/assets/overview` | 查看近期 crypto 标的 x 作者观点矩阵。 |
| 管理 | `/crypto/admin` | 管理员处理 crypto domain 的账号请求和任务。 |

顶部风险不放入 crypto 板块。现有 `/risk` 是美股顶部风险模块，只属于股票板块。

## 输入来源

第一版只要求支持 X 账号内容，输入仍来自统一内容记录：

| 字段 | 含义 |
| --- | --- |
| `platform` | 来源平台，第一版主要是 `x`。 |
| `account_name` | 本地账号名。 |
| `external_content_id` | 平台内容 ID。 |
| `url` | 原始内容链接。 |
| `title` | 标题或正文摘要。 |
| `body_text` | 正文。 |
| `publish_time` | 发布时间。 |
| `fetched_at` | 抓取时间。 |

Crypto 分析模块只处理已入库内容，不直接抓取外部平台。抓取策略、镜像、反爬和账号审批仍属于 X 账号抓取模块。

## AI 配置

AI 配置可以继续沿用项目现有配置来源：

1. `data/config/ai_settings.local.json`
2. 根目录 `.env`
3. 代码默认值

Crypto 使用独立 prompt 版本和独立 `analysis_version`：`crypto_signals_v1`。这样重分析、灰度和回滚不会影响股票分析结果。

## Prompt 口径

Crypto prompt 的目标不是复述帖子，而是抽取可以落到 crypto 投研面板里的推荐实体和信息信号。

Crypto 信息形态很分散，作者不一定会用标准 symbol 或直接写出买卖判断。AI 应关注“被推荐、被关注、被转发或被作为信息线索给出的实体”，而不是只抽取标准代币 symbol。

单条内容输出 JSON 对象，顶层字段：

| 字段 | 含义 |
| --- | --- |
| `summary_text` | 一句中文概括，说明该内容中的有效 crypto 推荐实体或信息信号；没有有效信号时写“未形成有效 crypto 信号”。 |
| `viewpoints` | 独立 crypto 推荐实体数组；没有有效信号时返回空数组。 |

每条观点包含：

| 字段 | 要求 |
| --- | --- |
| `entity_type` | 固定为 `crypto_entity`。 |
| `entity_name` | AI 识别出的推荐实体名称。可以是项目名、代币名、协议名、meme 名或账号名，不要求一定是标准 symbol。 |
| `entity_code_or_name` | 原文中用于识别该实体的主标识。可以是项目名、symbol、合约地址、项目账号、meme ticker 或其他原文写法。 |
| `entity_identifier_type` | `project_name`、`symbol`、`evm_contract`、`solana_address`、`project_account`、`meme_ticker` 或 `unknown`。 |
| `raw_identifiers` | 原文出现过的相关标识数组，例如 `uPEG_ETH`、`uPEG`、`0x...abcd`、Solana 地址、`@xxx`。 |
| `direction` | 作者本人方向。可用 `positive`、`negative`、`neutral`、`mixed` 或 `unknown`；单纯转发、提及和播报可以是 `unknown`。 |
| `stance` | 兼容 UI 的派生字段，可用 `strong_bullish`、`bullish`、`neutral`、`bearish`、`strong_bearish`、`mention_only`、`unknown` 等。 |
| `signal_type` | `explicit_stance`、`logic_based`、`informational` 或 `mention_signal`。 |
| `judgment_type` | `direct`、`implied`、`quoted`、`factual_only`、`mention_only` 或 `unknown`。 |
| `conviction` | `strong`、`medium`、`weak`、`none` 或 `unknown`。 |
| `evidence_type` | 见下方 crypto 证据类型。 |
| `logic` | 对有方向观点写清“基于什么证据 -> 得出什么标的结论”；对转发、提及、播报写清这个实体为什么值得进入面板。 |
| `evidence` | 能支撑判断的原文依据，贴近原文但不要大段照抄。 |
| `time_horizon` | `short_term`、`medium_term`、`long_term` 或 `unspecified`。 |

Crypto 支持的证据类型：

| 类型 | 用途 |
| --- | --- |
| `price_action` | 价格走势、突破、回撤、相对强弱。 |
| `technical` | 技术形态、指标、区间、支撑阻力。 |
| `onchain` | 链上活跃度、地址、TVL、费用、持仓变化等。 |
| `tokenomics` | 代币经济、供给、通胀、销毁、质押收益。 |
| `unlock` | 解锁、释放、归属期、抛压。 |
| `ecosystem` | 生态增长、应用、开发者、合作方。 |
| `protocol_revenue` | 协议收入、费用、现金流或利润。 |
| `catalyst` | 事件催化，如升级、主网上线、ETF、空投确认。 |
| `listing` | 上所、下架、交易对变化。 |
| `liquidity` | 流动性、深度、做市、稳定币流入流出。 |
| `funding_rate` | 合约资金费率、杠杆、持仓量。 |
| `security_incident` | 攻击、漏洞、暂停、审计风险。 |
| `regulation` | 监管、诉讼、政策。 |
| `macro` | 利率、美元、流动性、风险偏好。 |
| `position` | 作者披露仓位、加仓、减仓、止盈止损。 |
| `other` | 其他可解释证据。 |
| `unknown` | 证据类型不明。 |

## 有效观点规则

一个有效 crypto 观点或信息信号必须满足：

- 标的是可识别的 crypto 推荐实体。
- 实体可以通过项目名、代币 symbol、合约地址、Solana 地址、项目账号、meme ticker 或协议名识别。
- 有方向观点优先保留，`direction` 为 `positive` 或 `negative`。
- 没有明确方向但属于作者主动转发、提及、播报或聚合的信息，也可以保留为弱信号。
- `signal_type` 可以是 `explicit_stance`、`logic_based`、`informational` 或 `mention_signal`。
- `judgment_type` 可以是 `direct`、`implied`、`quoted`、`factual_only` 或 `mention_only`，但必须说明保留原因。
- 观点或信号能映射到归一化后的 crypto 推荐实体；不能可靠归一化时使用原文主标识生成稳定临时 `asset_key`，先进入前端可见结果，后续通过别名配置合并。

应保留的例子：

- 作者明确说看好、买入、加仓、布局、继续持有某个代币。
- 作者明确说看空、卖出、减仓、避开某个代币。
- 作者没有直接喊单，但通过链上、代币经济、生态、技术面等证据组织出明确可交易方向。
- 作者转述项目方或机构信息后，明确表达自己因此看多或看空。
- 作者转发某个项目、代币、合约地址、项目账号或 meme ticker，即使没有附带明确观点。
- 作者只是播报某个项目的公告、上线、活动、数据、融资、合作或异常事件，但该实体明确可识别。
- 作者只提到项目名、CA、Solana 地址、`@项目账号`、`$symbol` 或 meme ticker，但上下文表明这是一个 crypto 信息线索。

应过滤的例子：

- 空投教程、交互教程、白名单、邀请码、撸毛流程。
- NFT、铭文、meme 文化讨论，除非作者明确把它转成某个可识别 crypto 标的的方向性判断。
- 只讨论区块链公司股票、矿企股票、交易所股票或 crypto-stock，应归股票板块。
- 只讨论宏观、美元、利率、风险偏好，没有落到具体 crypto 标的。

## 标的归一化

Crypto 需要独立别名配置，不应复用 `security_aliases.json`。

配置文件：

- `data/config/crypto_aliases.json`
- `data/config/crypto_aliases.example.json`

归一化字段：

| 字段 | 含义 |
| --- | --- |
| `asset_key` | 稳定内部 key。优先使用项目或资产的规范名；无法确认时可使用安全的临时 key。 |
| `display_name` | 页面展示名，例如 `Bitcoin`、`uPEG_ETH` 或项目账号名。 |
| `symbol` | 可选标准 symbol，例如 `BTC`；没有可靠 symbol 时留空。 |
| `contract_addresses` | 可选合约地址数组，支持 EVM `0x...`、Solana 地址等。 |
| `x_accounts` | 可选项目账号数组，例如 `@xxx`。 |
| `aliases` | 常见别名，例如 `$BTC`、`bitcoin`、`比特币`、`uPEG_ETH`、`uPEG`、CA 简写。 |
| `category` | 可选分类，例如 L1、L2、DeFi、AI、Meme、Infra。 |
| `chain` | 可选主链或生态，例如 Ethereum、Solana、Base。 |
| `coingecko_id` | 可选外部价格或元数据 ID。第一版不强依赖。 |

归一化目标：

- 同一实体的项目名、symbol、合约地址、项目账号、meme ticker、中文名、英文名和美元符号写法尽量映射到同一个 `asset_key`。
- 页面展示优先使用 `display_name`，有可靠 symbol 时再展示 `symbol`。
- 没有可靠映射但原文标识明确的信号，会生成临时实体，不直接丢弃。
- 对易混淆 symbol、同名 meme、短 ticker 和不完整合约地址保持保守，不能靠模型猜测强行映射。

## 聚合结果

Crypto 使用独立实体和聚合表，避免和股票 `security_*` 命名混在一起；单条原文内容仍复用 `content_items`，避免同一条 X 内容重复抓取和存储。

当前 Supabase 表和等价逻辑：

| 表 | 用途 |
| --- | --- |
| `crypto_entities` | Crypto 标的、symbol、展示名、合约地址、项目账号、别名和归一化状态。 |
| `content_analyses` | 单条内容 AI 输出，使用 `analysis_domain='crypto'` 与股票结果并存。 |
| `content_viewpoints` | 单条内容拆出的 crypto 信号，使用 `analysis_domain='crypto'` 和 `entity_type='crypto_entity'`。 |
| `author_daily_summaries` | 作者每天的 crypto 细分信号，使用 `analysis_domain='crypto'`。作者页不展示日总结句。 |
| `crypto_entity_daily_views` | 标的每天被哪些作者如何提及或判断。 |
| `crawl_runs` | 每次 public worker 分析运行记录，使用 `analysis_domain` 区分。 |

第一版没有 `crypto_daily_prices`，也不写股票行情缓存。如果后续加行情，应单独设计数据源、刷新频率、缓存窗口和异常处理。

## 前端数据口径

Crypto 板块保持和股票板块一致的信息架构，但文案使用“标的”而不是“股票”。

`/crypto/feed`：

- 按作者维度展示 crypto 观点时间线。
- 登录用户只看到自己订阅范围。
- 未登录用户只看到公开轻量预览范围。
- 卡片里展示当天涉及的 crypto 标的、方向、逻辑、证据和原文链接。
- 不展示作者当天总括总结句。

`/crypto/assets`：

- 左侧快速切换 crypto 标的。
- 支持搜索和排序，例如最近日期、累计提及。
- 右侧展示标的身份标签、按日作者观点、逻辑、证据和来源。
- 不展示 K 线。

`/crypto/assets/overview`：

- 展示最近若干个有数据自然日的 crypto 标的 x 作者矩阵。
- 默认结束日是当前用户可见范围里的最新日期。
- 同一作者在窗口内多次提及同一标的时，每条信号作为独立点返回，不合并为单个观点。
- 绿点表示 `positive`，红点表示 `negative`，灰点表示 `unknown`、`neutral`、转发、提及、公告或数据播报等弱信号。

## 账号和订阅边界

Crypto 板块可以复用现有账号审批和订阅模型，但需要明确账号属于哪个板块。

第一版支持：

- 一个 X 账号可以只属于股票板块。
- 一个 X 账号可以只属于 crypto 板块。
- 一个 X 账号也可以同时属于两个板块，但两边使用不同 prompt 分析，结果互不污染。

提交账号时应能标记目标板块。管理员审批时应能确认账号板块，否则股票和 crypto 的账号库会混在一起。

## 运行和重分析语义

Crypto 应有独立命令或独立参数，避免误触股票重分析。

命令语义：

| 命令形态 | 作用 |
| --- | --- |
| `public-reanalyze-recent --domain crypto --days N --clear-analysis` | 对最近 N 个上海自然日的 crypto domain 内容强制重新生成 crypto 观点。 |
| `public-rebuild-timelines --domain crypto` | 基于已有 crypto 分析重建作者时间线和标的聚合。 |
| `normalize-crypto-assets --days N` | 根据 `crypto_aliases.json` 重新归一化并重建 crypto 标的视图。 |

抓取任务通过 `crawl_jobs.domain` 区分。定时任务默认可为 `stock` 和 `crypto` 分别入队；服务端可用 `PUBLIC_WORKER_DOMAINS=stock,crypto` 控制启用板块。

## 权限和公开预览

权限口径复用股票板块：

- 未登录用户可看账号库和少量公开预览。
- 登录用户按自己的订阅范围查看完整时间线。
- 管理功能只对管理员邮箱显示。
- 公开 RPC 或 API 必须按板块和订阅关系过滤。

需要避免的情况：

- 用户订阅了股票账号，却自动看到同账号的 crypto 分析。
- 未登录预览跨板块泄露更多内容。
- 管理入口暴露给非管理员。

## 与股票板块的关系

Crypto 模块和股票模块共享的部分：

- X 账号抓取基础设施。
- `content_items` 原文内容表，同一条 X 内容只存一次。
- 登录、账号审批和订阅能力。
- AI client 和 JSON 校验框架。
- 作者时间线和标的一览表的交互模式。

Crypto 模块必须独立的部分：

- Prompt 和 `analysis_version`。
- `analysis_domain` 写入、重建和 RPC 可见范围。
- 标的实体类型和别名配置。
- 聚合表或板块过滤字段。
- 页面文案和路由。
- 是否接行情、K 线、风险指标的决策。

不能直接复用的部分：

- 股票 prompt。
- `security_aliases.json`。
- `security_daily_prices` 和股票 K 线逻辑。
- 美股顶部风险 `/risk`。

## 后续可扩展方向

以下方向不属于第一版，但可以预留接口：

- Crypto 行情和 K 线。
- Crypto 风险面板。
- 链上指标解释和证据展示。
- 标的分类视图，例如 L1、DeFi、AI、Meme。
- 情绪聚集、同标的多账号共识和分歧。
- 账号按 crypto 专长标签分组。

这些扩展应在第一版 crypto 观点闭环稳定后再做，避免把分析、行情、链上、风控和交易执行一次性混进同一个模块。

## 设计约束

- Crypto 第一版只做观点抽取、弱信号保留和聚合展示。
- 有方向、有逻辑、转发、提及、公告和数据播报都可以作为 crypto 标的信号进入前端。
- AI 输出必须经过结构校验、观点过滤和 crypto 标的归一化。
- 股票、crypto-stock 和美股顶部风险继续留在股票板块。
- 聚合视图必须可重建，不能依赖一次性不可复现状态。
- 前端可见范围必须尊重登录、订阅和板块边界。
- API key、数据库 URL、本地 snapshot 和运行时缓存不提交 Git。
