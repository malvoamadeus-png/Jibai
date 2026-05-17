# 账号内容观点分析

## 模块边界

本模块负责把已抓取内容转成结构化观点，并按作者、股票和日期生成可浏览的聚合视图。它不负责抓取账号内容，也不负责美股顶部风险预判。

现有入口：

```bash
python backend/src/main.py run-once --config data/config/watchlist.json
python backend/src/main.py run-once-x --config data/config/x_watchlist.json
python backend/src/main.py reanalyze-existing
python backend/src/main.py normalize-securities
```

相关代码：

- `backend/packages/ai/pipeline.py`
- `backend/packages/ai/client.py`
- `backend/packages/ai/prompts.py`
- `backend/packages/common/database.py`
- `backend/packages/common/security_aliases.py`
- `backend/src/jobs.py`

## 输入

分析模块的输入是 SQLite 中的统一内容记录，主要来自：

- 小红书抓取模块
- X 账号抓取模块

统一内容模型为 `RawNoteRecord`，入库位置为 `content_items`。关键字段：

| 字段 | 含义 |
| --- | --- |
| `platform` | 来源平台，如 `x` 或 `xhs` |
| `account_name` | 本地账号名 |
| `external_content_id` | 平台内容 ID |
| `url` | 原始内容链接 |
| `title` | 标题或正文摘要 |
| `body_text` | 正文 |
| `publish_time` | 发布时间 |
| `fetched_at` | 抓取时间 |

## AI 配置

AI 配置优先级：

1. `data/config/ai_settings.local.json`
2. 根目录 `.env`
3. 代码默认值

`/control` 页面保存的配置会写入 `data/config/ai_settings.local.json`。API key 输入框留空保存表示保留旧 key，不会回显已保存 key。

## 分析流程

1. 读取所有已入库内容。
2. 根据 `analysis_version` 判断哪些内容需要补分析或重分析。
3. 对每条待处理内容调用 AI，生成 JSON。
4. 校验 JSON 必需字段。
5. 解析结构化观点 `ViewpointRecord`。
6. 用 `security_aliases.json` 归一化股票名称、ticker 和市场。
7. 写入 `content_analyses` 和 `content_viewpoints`。
8. 按作者、日期聚合为 `author_daily_summaries`。
9. 按股票、日期聚合为 `security_daily_views`。
10. 轻量刷新相关股票近期行情，写入 `security_daily_prices`。轻量刷新只控制本次抓取最近几天的数据，不能把日线缓存裁剪到轻量窗口；公开 K 线仍保留 180 天缓存窗口。
11. 生成本地 snapshot，写入 `data/runtime/ai/snapshots/`。

公开 Supabase worker 的分析重建窗口默认是 30 个上海自然日，和初始回填的 30 天内容窗口一致。定时抓取可以只抓较少新帖，但清空并重建分析表时不能只用 1 到 3 天窗口，否则作者时间线会被重建成只剩最近几天。

## 观点结构

一个有效股票观点必须满足：

| 字段 | 要求 |
| --- | --- |
| `entity_type` | 当前只保留 `stock` |
| `direction` | 必须是 `positive` 或 `negative` |
| `signal_type` | 必须是 `explicit_stance` 或 `logic_based` |
| `judgment_type` | 不能是 `factual_only`、`quoted`、`mention_only` |
| `conviction` | `strong`、`medium`、`weak`、`none` 或 `unknown` |
| `evidence_type` | 财报、估值、技术、宏观、资金流等证据类型 |
| `time_horizon` | `short_term`、`medium_term`、`long_term` 或 `unspecified` |

只提及股票但没有方向性判断的内容会被过滤，不进入核心观点聚合。

## 聚合结果

| 表 | 用途 |
| --- | --- |
| `content_analyses` | 单条内容的 AI 摘要和原始响应 |
| `content_viewpoints` | 单条内容拆出的结构化观点 |
| `security_entities` | 股票实体和别名 |
| `security_mentions` | 兼容旧结构的股票提及记录 |
| `author_daily_summaries` | 作者每天的观点摘要 |
| `security_daily_views` | 股票每天被哪些作者如何看待 |
| `security_daily_prices` | 股票日线价格缓存，公开 K 线按 180 天窗口读取 |
| `analysis_runs` | 每次分析运行记录 |

## 公开股票视图

公开前端有两个股票入口：

- `/stocks` 为“按股票（详情）”，按单只股票展示 K 线、日线标记和按日作者观点。
- `/stocks/overview` 为“按股票（一览表）”，按最近 7 个有数据自然日展示股票 × 作者矩阵。

详情页的快速切换列表由 `list_visible_entities` 返回，支持按最近日期或累计提及排序，且不应再使用最近 2 到 3 天的硬编码截断。可见历史由 `security_daily_views` 中已物化的股票观点决定。

一览表由 `get_visible_stock_matrix` 返回。默认结束日是当前用户可见范围里的最新 `date_key`，窗口为结束日往前 7 个自然日。登录用户只显示自己订阅账号的观点；未登录用户仍只看到公开预览范围。同一作者在窗口内多次提及同一股票时，每条有效观点都作为独立红/绿点返回，不合并为单个观点。

## 股票归一化

股票别名配置位于 `data/config/security_aliases.json`，示例文件为 `data/config/security_aliases.example.json`。

归一化目标：

- 同一股票的中文名、英文名、ticker、别名映射到同一个 `security_key`。
- 页面展示使用配置中的 `display_name`。
- 没有可靠映射的观点不进入核心股票视图。

## 重跑语义

| 命令 | 作用 |
| --- | --- |
| `run-once` | 小红书抓取后分析 |
| `run-once-x` | X 抓取后分析 |
| `reanalyze-existing` | 对现有内容强制重新生成 AI 观点 |
| `normalize-securities` | 根据别名配置重新归一化并重建视图 |

## 设计约束

- 分析模块只处理已入库内容，不直接抓取外部平台。
- AI 输出必须经过结构校验和观点过滤。
- 股票观点只保留有方向、有逻辑或明确态度的内容。
- 聚合视图可重建，不能依赖一次性不可复现状态。
- API key 和本地 snapshot 不提交 Git。
