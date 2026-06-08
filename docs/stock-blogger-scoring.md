# 股票博主观点验证评分方案

## 模块定位

本模块用于验证股票博主历史观点的后验表现，回答：

- 某位博主在提到某只股票后，后续 1、5、20 个交易日是否产生了方向正确的超额收益。
- 这位博主更擅长短线、周线还是月线级别判断。
- 这位博主的持续提及是在强化正确认知，还是在持续固执地看错。

本模块不直接生成买卖建议，不把评分解释为未来收益保证。产品命名建议使用“观点历史表现”或“观点验证评分”，避免使用“预测准确率”这种绝对裁判式表达。

第一版目标是先对指定 3 个 X 账号做测试，跑通抽取、行情、评分、报告和样本解释链路。

## 和现有模块的关系

现有股票观点主线已经抽取以下字段：

| 字段 | 用途 |
| --- | --- |
| `direction` | 作者本人对股票的方向，股票主线只保留 `positive` / `negative`。 |
| `signal_type` | `explicit_stance` 或 `logic_based`。 |
| `judgment_type` | `direct` / `implied` 等，过滤 `factual_only`、`quoted`、`mention_only`。 |
| `conviction` | `strong`、`medium`、`weak`、`none`、`unknown`。 |
| `time_horizon` | `short_term`、`medium_term`、`long_term`、`unspecified`。 |
| `logic` / `evidence` | 观点逻辑和原文证据。 |

评分模块优先从 `content_items` + `content_viewpoints` 构造“观点事件”，因为这里保留原始内容、原始链接和 `publish_time`。不要只依赖 `security_daily_views`，后者是按日期聚合结果，适合页面展示，但不够表达精确发言时间。

`tools/audit/x_account_stock_audit/` 已有隔离研究工具，当前按 `bull/bear` 计算 1/5/20 交易日方向收益。新的博主评分方案可以吸收它的抓取、抽取、报告思路，但主线路径、表结构和部署流程不能直接依赖该研究工具。

## 有效观点事件

一个可评分事件至少包含：

| 字段 | 说明 |
| --- | --- |
| `author_key` | 平台 + 账号的稳定键。 |
| `content_id` / `note_id` | 原始内容 ID。 |
| `source_url` | 原文链接。 |
| `published_at` | 原始发布时间，必须保留到具体时间。 |
| `security_key` | 归一后的股票键。 |
| `ticker` / `market` | 行情拉取需要的标识。 |
| `direction` | `positive` 或 `negative`。 |
| `signal_type` | `explicit_stance` 或 `logic_based`。 |
| `judgment_type` | `direct` 或可信的 `implied`。 |
| `conviction` | `strong`、`medium`、`weak`、`unknown`。 |
| `time_horizon` | 作者表达的周期，不作为第一版过滤条件。 |
| `logic` / `evidence` | 后续解释评分时展示。 |

过滤规则：

- 只评分 `direction in positive/negative` 的观点。
- 只评分 `signal_type in explicit_stance/logic_based` 的观点。
- `factual_only`、`quoted`、`mention_only` 不评分。
- `mixed` 或同一条里方向不可压缩的观点先不评分，但可以保留在报告里解释“未计分”。
- 没有可靠 `security_key` 或缺行情数据的观点不进入正式得分，只计入 `unscored_count`。

## 客观分析型表达怎么处理

观点强度不等于喊单语气。很多质量较高的博主不会写“必涨”“梭哈”，而是写产业链位置、竞争格局、订单、利润率、估值或管理层信号，然后得出“看好/继续持有/值得布局/不看好”的结论。

因此第一版沿用现有字段，但解释口径要更清楚：

| 档位 | 判定方式 |
| --- | --- |
| `strong` | 不要求夸张喊单。只要结论非常明确，并且有较强逻辑链、目标价、仓位动作、明确催化、持续高确信 thesis，均可为强。 |
| `medium` | 有清楚的看多/看空结论和理由，但语气保留，或没有仓位/目标价/强催化。客观分析型“我看好，因为竞争格局改善”通常至少是这一档。 |
| `weak` | 只是“关注”“可能有机会”“倾向于”“需要观察”，方向存在但不坚定。 |
| `unknown` | 模型能确认方向，但无法稳定判断强度；参与评分但权重略低。 |
| `none` | 没有观点强度，通常不应进入可评分事件。 |

`logic_based` 不自动比 `explicit_stance` 更高分，也不自动更高权重；它只是说明观点来自论证链。评分的核心仍是后续超额收益和样本稳定性。

第一版建议把 `conviction` 作为事件权重，而不是直接改变收益本身：

| `conviction` | 事件权重 |
| --- | ---: |
| `strong` | 1.25 |
| `medium` | 1.00 |
| `unknown` | 0.85 |
| `weak` | 0.65 |

这样强观点看对会更影响加分，看错也更影响扣分；客观但清晰的 `medium` 观点不会因为没有喊单词而被轻视。

## 重复提及规则

AI 股票账号会高频反复提同一批核心股票。第一版按下面规则处理：

- 跨交易日重复提及同一只股票，保留为独立观点事件。
- 如果作者持续看多后股票持续跑赢，应持续加分。
- 如果作者持续看多但股票持续跑输，也应持续扣分，体现认知没有及时转变。
- 同一作者、同一股票、同一交易日、同一方向的多条内容合并为一个可评分事件，避免一天刷屏放大样本数。
- 合并事件保留全部 `note_ids`、`source_urls`、最高 `conviction`、合并后的 `logic/evidence`。
- 同一作者、同一股票、同一交易日内出现相反方向：
  - 如果后发内容明确表达观点反转，可以按最新方向生成一个事件，并在 `metadata.reversal=true` 标记。
  - 如果只是正反因素混杂，标记为 `mixed_same_day`，第一版不评分。

第一版不做跨日冷却期，不对连续多日观点降权。后续如果发现单一作者每天机械重复同一句导致样本失真，再增加 `streak_id`、`streak_length` 和“连续段落视图”，但不影响逐日事件明细。

## 发言时间和交易日锚点

必须保留原始 `published_at`，并派生：

| 字段 | 说明 |
| --- | --- |
| `published_at_utc` | 标准 UTC 时间。 |
| `exchange_timezone` | 股票主要交易所时区，美股通常是 `America/New_York`。 |
| `event_trading_day` | 该观点归属的交易日。 |
| `anchor_trading_day` | 用于计算 forward return 的起点交易日。 |
| `anchor_price` | 起点价格。 |
| `anchor_price_kind` | `same_day_open`、`same_day_close_estimate`、`next_day_open` 等。 |

第一版可以先使用日线 OHLC，保留时间字段，为未来接入分钟线做准备。

日线近似锚点建议：

| 发言时间 | 起点价格 |
| --- | --- |
| 交易日盘前 | 当日 open。 |
| 交易时段内 | 当日 close，标记为 `same_day_close_estimate`。 |
| 交易日收盘后 | 下一交易日 open。 |
| 周末或休市日 | 下一交易日 open。 |

`same_day_close_estimate` 是近似值，不代表发言瞬间可成交价格。报告中要展示 `anchor_price_kind`，避免把日线近似误解为逐笔回测。

如果起点价格是 open，则 `1d` 目标价使用同一交易日 close；如果起点价格是 close，则 `1d` 目标价使用下一交易日 close。`5d` 和 `20d` 依此按完成的交易 session 计数。

如果后续接入分钟线，交易时段内应改为“发言时间之后的第一根可用分钟 K 或下一个合理成交点”，并重新计算事件收益。

## 评分周期和历史窗口

第一版固定评分周期：

- `1d`：1 个交易 session 后。
- `5d`：5 个交易 session 后。
- `20d`：20 个交易 session 后，近似一个月。

所有周期都按交易日，不按自然日。

内容抓取窗口：

- 第一版测试 3 个账号，默认拉取最近 90 个自然日内容。
- 90 个自然日大致覆盖 60 多个交易日，可以让较早事件具备完整 20d 评分。
- 价格数据至少拉取 180 个自然日或等价交易日缓存，确保事件前后都有可用行情。
- 若未来增加 60d 评分，内容窗口建议扩到至少 180 个自然日。

成熟度规则：

- 未到 1/5/20 个交易日的事件，对应周期记为 `pending`。
- `pending` 事件不参与该周期评分。
- 总分要展示 `matured_count` 和 `pending_count`，避免近期大量观点让评分看起来缺失或偏短线。

## 收益口径

评分使用超额收益，不只看绝对涨跌。

第一版大盘基准：

- A 股默认使用科创50指数 `000688` 作为基准。
- 如果指数源不可用，工程 fallback 到科创50 ETF `588000`，报告必须标明实际使用的 `benchmark_symbol`。
- A 股之外的美股、港股、台股、韩股和其他 Yahoo 可取价市场，统一使用美股基准。
- 美股基准默认使用纳斯达克综合指数 `^IXIC`。
- 如果数据源无法稳定返回指数，工程上可以用 `QQQ` 作为 fallback，但报告必须标明 `benchmark_symbol=QQQ`，不能混写成纳指。
- 如果基准缺失，对应周期标记 `missing_price`，不进入该周期评分；不要回退成只看绝对涨跌。

每个事件、每个周期计算：

```text
stock_return_h = target_price_h / anchor_price - 1
benchmark_return_h = benchmark_target_price_h / benchmark_anchor_price - 1
excess_return_h = stock_return_h - benchmark_return_h

direction_sign = +1  if direction == positive
direction_sign = -1  if direction == negative

directional_excess_h = direction_sign * excess_return_h
```

解释：

- 看多后股票跑赢纳指，`directional_excess_h > 0`，加分。
- 看多后股票上涨但跑输纳指，`directional_excess_h < 0`，扣分或不给高分。
- 看空后股票下跌，或涨得明显少于纳指，`directional_excess_h > 0`，加分。
- 看空不等于做空；这里评价的是“回避/负向判断是否带来相对优势”。

价格优先使用复权价格。若行情源只提供未复权 OHLC，需要在报告里标记 `adjustment_status=unknown`，并把拆股、分红附近的评分列为低可信。

## 单次事件得分

第一版事件层只保留连续值指标：

| 指标 | 用途 |
| --- | --- |
| `directional_excess_h` | 最重要的连续值指标，表达方向正确后的超额收益。 |
| `score_h` | 按周期单位换算后的分数，用于聚合排序。 |

事件分不设上下限。`score_scale_h` 只表示“多少方向超额收益对应 100 分”，不是封顶阈值：

| 周期 | score scale |
| --- | ---: |
| `1d` | 5 个百分点 |
| `5d` | 10 个百分点 |
| `20d` | 20 个百分点 |

```text
score_h = directional_excess_h / score_scale_h * 100
```

例子：

```text
1d 方向超额收益 +5%      => score_1d = 100
1d 方向超额收益 +20%     => score_1d = 400
1d 方向超额收益 +10000%  => score_1d = 200000
```

`score_scales` 必须放在配置里，不要写死在业务逻辑里。当前代码读取旧配置时允许 `score_caps` 作为兼容 fallback，但新配置和文档统一使用 `score_scales`。

## 周期权重

第一版总分周期权重：

| 周期 | 权重 |
| --- | ---: |
| `1d` | 20% |
| `5d` | 35% |
| `20d` | 45% |

权重要配置化，例如：

```json
{
  "horizons": [1, 5, 20],
  "horizon_weights": {
    "1d": 0.20,
    "5d": 0.35,
    "20d": 0.45
  },
  "benchmark_symbol": "^IXIC",
  "benchmark_fallback_symbol": "QQQ",
  "a_share_benchmark_symbol": "000688",
  "a_share_benchmark_fallback_symbol": "588000",
  "a_share_benchmark_extra_symbols": [],
  "history_days": 90,
  "min_ranked_events": 10
}
```

调整权重只应影响重新聚合评分，不应要求重新抽取 AI 观点。也就是说，观点事件和收益明细要独立保存，评分 snapshot 可以随配置重算。

## 博主聚合评分

主榜必须避免“同一天提更多股票就自然更高分”。因此作者分采用两级归一化：

```text
作者-日期-周期分 = 当天所有该周期已成熟事件分按 conviction 权重平均
作者周期分 = 所有已成熟观点日的平均
综合分 = 1d * 20% + 5d * 35% + 20d * 45%
```

如果某个周期没有已成熟事件，则该周期不参与综合分的加权平均。样本量只作为展示信息，不参与分数。

按作者聚合时，至少输出：

| 指标 | 说明 |
| --- | --- |
| `overall_score` | 唯一综合分，按观点日归一化后由 1/5/20 周期权重聚合。 |
| `score_1d` / `score_5d` / `score_20d` | 分周期表现。 |
| `avg_directional_excess_*` | 平均方向超额收益。 |
| `event_count` | 可评分观点事件数。 |
| `scored_event_count` | 至少一个周期已评分的事件数。 |
| `scored_day_count` | 至少一个周期已评分的观点日数。 |
| `scored_day_count_*` | 每个周期已评分观点日数。 |
| `matured_count_*` | 每个周期已成熟样本数。 |
| `pending_count_*` | 每个周期待成熟样本数。 |
| `positive_count` / `negative_count` | 看多/看空样本数量。 |
| `strong_count` / `medium_count` / `weak_count` | 强度分布。 |
| `best_horizon` | 相对最擅长的周期。 |
| `worst_horizon` | 相对最弱周期。 |
| `top_contributors` | 对总分影响最大的正负事件，用于解释。 |

排序只使用 `overall_score` 降序。样本天数、事件数和待成熟数量可以在前端作为提示状态展示，但不要改变排序分。

## 持续提及画像

因为跨日重复提及会分开计分，报告还应该补充持续性指标，避免只看总分：

| 指标 | 说明 |
| --- | --- |
| `streak_count` | 同一作者连续多日同方向提同一股票的段落数量。 |
| `avg_streak_length` | 平均连续提及天数。 |
| `streak_score` | 连续段落内的平均方向超额收益。 |
| `reversal_count` | 作者对同一股票发生方向反转的次数。 |
| `late_reversal_cases` | 股票已经明显跑输后仍持续看多，或明显跑赢后仍持续看空的案例。 |

第一版可以先不把这些指标纳入总分，只在报告里作为解释视图。

## 重要边界和处理方式

### 行业 Beta

纳指基准能过滤大盘环境，但不能过滤半导体、软件、核电、电力等行业 Beta。第一版先按纳指做统一基准；第二版再考虑：

- 半导体：`SMH` 或 `SOXX`
- 软件：`IGV`
- 云/AI 基建：可配置 ETF 或自定义篮子

届时可以同时展示“相对纳指”和“相对行业”的两套超额收益。

### 时间周期和作者原意

作者如果明确写“长期看好”，20d 只代表早期验证，不代表完整 thesis 已兑现。第一版仍统一计算 1/5/20，但页面要展示 `time_horizon`，避免把长期观点的 1d 表现过度解读。

第二版可以按 `time_horizon` 调整权重：

- `short_term`：提高 1d/5d 权重。
- `medium_term`：提高 5d/20d 权重。
- `long_term`：降低 1d 权重，并要求更长历史窗口。

### 删除和改帖

如果原平台内容删除，已抓取内容和观点事件不应自动删除，否则评分容易被操纵。可以增加 `source_available_status`，但历史评分仍保留。

### 引用和转述

转述管理层、机构或别人观点不自动评分。只有作者明确表达“因此我看好/持有/买入/卖出/避开”，才作为作者本人观点事件。

### 目标价和条件判断

第一版不处理目标价兑现率，也不评分条件触发类观点。

示例：

- “突破 120 后我才看多”：标记为条件观点，第一版不评分。
- “目标价 150”：第一版按方向评分，目标价达成类指标留到第二版。

### 财报和重大事件

观点发出后遇到财报、监管、收购等重大外部事件，评分仍先保留，因为投资判断本身包含事件风险。但报告可以标记 `event_risk_window`，未来再考虑单独分析财报前后样本。

### 多市场股票

第一版重点服务 AI 美股账号，但评分工具已经支持多市场基准口径：A 股使用 `000688` / `588000`，A 股之外统一使用美股基准。若个股或基准行情缺失，只展示未评分原因，不把绝对涨跌混入超额收益评分。

## 配置建议

建议新增独立配置文件，例如 `data/config/stock_blogger_scoring.example.json`：

```json
{
  "history_days": 90,
  "price_days": 180,
  "benchmark_symbol": "^IXIC",
  "benchmark_fallback_symbol": "QQQ",
  "a_share_benchmark_symbol": "000688",
  "a_share_benchmark_fallback_symbol": "588000",
  "a_share_benchmark_extra_symbols": [],
  "horizons": [1, 5, 20],
  "horizon_weights": {
    "1d": 0.2,
    "5d": 0.35,
    "20d": 0.45
  },
  "score_scales": {
    "1d": 0.05,
    "5d": 0.1,
    "20d": 0.2
  },
  "conviction_weights": {
    "strong": 1.25,
    "medium": 1.0,
    "unknown": 0.85,
    "weak": 0.65
  },
  "min_ranked_events": 10,
  "full_confidence_events": 30
}
```

示例配置已落在 `data/config/stock_blogger_scoring.example.json`，首批测试账号为：

- `@labubu_trader`
- `@hicagr`
- `@xiaomustock`

本地私有账号列表、API key、数据库 URL 不放入非 example 配置。

## 第一版实现拆分

第一版离线工具位于 `tools/stock_blogger_scoring/`，按四层实现：

1. `ai_extract` + `scoring.build_signal_events`
   - 从 X 发言抽取股票观点，再生成可评分事件。
   - 处理同日合并、方向冲突、时间锚点、股票归一化状态。

2. `market.score_events`
   - 拉取或读取个股日线、纳指日线。
   - 计算 1/5/20 交易日绝对收益、基准收益和方向超额收益。
   - 标记 `pending`、`missing_price`、`unsupported_benchmark`。

3. `scoring.aggregate_author_scores`
   - 按作者、观点日、周期、方向、强度聚合。
   - 先生成作者-日期-周期分，再生成作者周期分和唯一综合分。
   - 保留评分天数、事件数、待成熟数量和贡献事件作为解释信息。

4. `report`
   - 输出 JSON/HTML/Excel 或前端所需 snapshot。
   - 第一版测试 3 个账号时，优先输出可人工复核的事件明细和解释。

离线工具继续用于审计和回归；正式前后端接入使用 `backend/packages/public_app/stock_blogger_scoring.py`
从 Supabase 主库生成 snapshot，不依赖 `tools/` 或 `data/runtime/`。

运行命令：

```bash
PYTHONPATH=backend:. python tools/stock_blogger_scoring/cli.py run
```

常用参数：

```bash
PYTHONPATH=backend:. python tools/stock_blogger_scoring/cli.py run \
  --config data/config/stock_blogger_scoring.example.json \
  --days 90 \
  --model gpt-5.4-mini
```

如果已经有 `stock_signal_mentions.jsonl`，可用 `--resume --skip-ai` 只重算行情和评分；如果只想验证流程，可加 `--skip-market` 跳过行情。

正式公开站重建命令：

```bash
PYTHONPATH=backend python backend/src/main.py public-ensure-stock-blogger-accounts
PYTHONPATH=backend python backend/src/main.py public-rebuild-stock-blogger-scores --days 90
```

点金榜正式链路当前默认停用，不主动拉取或重建评分数据：

- `public-web` 只有设置 `NEXT_PUBLIC_STOCK_BLOGGER_GOLD_FETCH_ENABLED=true`
  时才会请求 `get_stock_blogger_gold_rankings()`。
- 长驻 public worker 只有设置 `PUBLIC_STOCK_BLOGGER_SCORE_ENABLED=true`
  时才会按 `PUBLIC_WORKER_STOCK_BLOGGER_SCORE_TIME` 重建快照，默认时间
  `23:10` Asia/Shanghai。
- 默认停用时，scheduled stock crawl 不会因为点金榜白名单额外抓取账号；
  账号如果通过订阅等其他正式路径进入，仍按原有抓取流程处理。

评分账号由 `PUBLIC_STOCK_BLOGGER_SCORE_ACCOUNTS` 配置，默认：

- `labubu_trader`
- `hicagr`
- `xiaomustock`

## 正式前后端接入

Supabase snapshot 表：

| 表 | 说明 |
| --- | --- |
| `stock_blogger_score_runs` | 每次评分 run、窗口、配置、状态和错误摘要。 |
| `stock_blogger_author_scores` | 作者综合分、分周期分、评分天数、事件数、pending、方向/强度分布。 |
| `stock_blogger_score_events` | 展开明细事件，含股票、方向、强度、锚点和各周期收益/分数。 |

公开 RPC：

- `get_stock_blogger_gold_rankings()` 返回最新成功 run。
- 只 grant 给 `authenticated`；前端未登录时不调用 RPC。
- payload 不包含 `hit`、`hit_rate`、`confidence_factor`、`raw_overall_score`。

公开前端：

- 页面：`public-web` 的 `/stocks/gold`。
- 导航：股票板块二级入口 `点金榜`。
- 当前默认不拉取点金榜后端数据；开启
  `NEXT_PUBLIC_STOCK_BLOGGER_GOLD_FETCH_ENABLED=true` 后才展示 RPC 数据。
- 主榜不展示具体标的和逻辑；点击作者行展开后展示股票、日期、方向、强度、周期分和状态。

## 建议输出

离线测试输出目录可以放在 `data/runtime/stock_blogger_scoring/{run_id}/`：

| 文件 | 说明 |
| --- | --- |
| `signal_events.jsonl` | 每条可评分或未评分观点事件。 |
| `forward_returns.jsonl` | 每个事件每个周期的收益明细。 |
| `author_scores.json` | 作者聚合评分。 |
| `stock_author_scores.json` | 作者 x 股票维度表现。 |
| `report.html` | 方便人工阅读的报告。 |
| `audit.xlsx` | Excel 明细，包括作者分、事件和 forward return。 |
| `manifest.json` | 配置、账号、时间窗口、模型版本和运行状态。 |

报告必须能从作者总分一路点到原文证据、观点时间、锚点价格、个股收益、纳指收益和计算后的超额收益。

## 第一版验收标准

- 能指定 3 个账号，拉取或读取最近 90 个自然日内容。
- 每个观点事件保留具体 `published_at` 和原文链接。
- 同一作者、同一股票、同一交易日、同方向只计一个事件。
- 跨交易日重复提及同一股票分开计分。
- 1/5/20 交易日收益按交易日计算，不按自然日。
- 美股评分包含纳指基准收益和方向超额收益。
- 未成熟周期显示 `pending`，不参与该周期得分。
- 权重、score scale、历史窗口都可以通过配置调整，调整后不需要重新抽取 AI 观点。
- 样本天数、事件数和待成熟数量作为提示信息展示，不参与综合分。
