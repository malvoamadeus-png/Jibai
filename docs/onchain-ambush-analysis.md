# 链上埋伏分析方案

## 模块状态

链上埋伏是股票、加密观点之后的第三个一级板块。当前第一版已按独立 `onchain_*` 表和 RPC 实现，不复用股票/crypto 的 X 账号 `domain` 模型。

本模块追踪“二段交易”地址：在新闻平稳、项目功能尚未完全发酵或市场溢价较低时买入，等待事件催化、产品进展或代币暴涨后再抛售的链上地址。

第一版只做持仓快照和日级变化，不做实时监控、交易执行、跟单或 AI 观点抽取。

## 页面

左侧 sidebar 有三个一级板块：

- `股票`
- `加密`
- `链上`

链上板块页面：

| 页面 | 路由 | 用途 |
| --- | --- | --- |
| 总览 | `/onchain` | 今日新买入、共识持仓、增持榜、地址活跃度和最近运行状态。 |
| 地址库 / 按人 | `/onchain/wallets` | 已审批地址列表、订阅、提交地址、私有备注、单地址 token x 日期矩阵。 |
| 按代币 | `/onchain/tokens` | token 为行、日期为列，支持数量、金额、括号持有人数、排序和链筛选。 |
| GMGN备注生成 | `/onchain/gmgn-labels` | 输入 token，调用 Linux API 查询 OKX Top 持仓/盈利地址，并在浏览器本地按用户原备注生成新增 GMGN 备注。 |
| 管理 | `/onchain/admin` | 审批地址、配置启用链、全站备注、手动抓取、运行状态。 |

地址显示优先级固定为：

1. 当前用户私有备注。
2. 管理员全站备注。
3. 缩略地址，例如 `0xa7bf...e1bc`。

普通列表不展示完整长地址。

## 支持链

| 展示名 | chain key | OKX `chainIndex` |
| --- | --- | --- |
| Ethereum | `ethereum` | `1` |
| Base | `base` | `8453` |
| BNB Smart Chain | `bsc` | `56` |
| Solana | `solana` | `501` |

普通用户订阅地址；管理员决定该地址实际抓取哪些链。代币不跨链自动合并，同一张表通过链 badge 和链筛选区分。

## 数据源

后端使用 OKX Web3 / OnchainOS：

- 接口：`/api/v6/dex/balance/all-token-balances-by-address`
- GMGN 备注接口：`/api/v6/dex/market/token/top-trader`、`/api/v6/dex/market/token/holder`、`/api/v6/dex/market/token/basic-info`
- 代码：`backend/packages/onchain/okx_client.py`
- GMGN 备注代码：`backend/packages/onchain/gmgn_labels.py`、`backend/packages/public_app/api.py`

OKX env 只在后端读取：

```bash
OKX_API_KEY=
OKX_SECRET_KEY=
OKX_PASSPHRASE=
```

可选运行参数：

```bash
PUBLIC_ONCHAIN_ENABLED=true
PUBLIC_ONCHAIN_FETCH_TIMES=04:20,10:20,16:20,22:20
PUBLIC_ONCHAIN_MIN_VALUE_USD=200
PUBLIC_ONCHAIN_EXCLUDE_RISK_TOKEN=true
OKX_TIMEOUT_SECONDS=30
OKX_MAX_RETRIES=4
OKX_REQUEST_DELAY_SECONDS=0.25
```

OKX `excludeRiskToken=0` 表示过滤风险空投和貔貅盘；代码同时保留本地 `isRiskToken` 二次过滤。

GMGN 备注生成只把 token address 和 `limit` 发到 Linux API；EVM/Solana 原备注只在浏览器本地解析、去重和生成 `NewLabel-*` 输出，不上传服务器。API 要求 Supabase 登录态 Bearer token，服务端用 `SUPABASE_URL` 和 `SUPABASE_ANON_KEY` 校验用户已登录。

## 过滤和身份

进入可见日级视图前过滤：

- 单地址、单链、单 token `holding_value_usd > PUBLIC_ONCHAIN_MIN_VALUE_USD`，默认 `200`。
- 过滤规则表中的稳定币和主流资产。
- 默认排除 OKX 标记的风险 token。

初始过滤规则写在 `supabase/migrations/018_onchain_ambush.sql`：

- 稳定币：`USDT`、`USDC`、`DAI`、`FDUSD`、`TUSD`、`USDE`、`SUSDE`、`USDS`、`PYUSD`。
- 主流资产：`ETH`、`WETH`、`STETH`、`WSTETH`、`WBTC`、`BTC`、`SOL`、`BNB`、`WBNB`、`CBETH`、`RETH`。

Token identity：

- 合约 token：`chainIndex + tokenContractAddress`
- 原生资产：`chainIndex + native + symbol`

增持以 token 数量变化为准；金额变化只作为独立展示和排序，不能推断真实增持。

## 表和 RPC

Migration：`supabase/migrations/018_onchain_ambush.sql`

表：

| 表 | 用途 |
| --- | --- |
| `onchain_wallets` | 地址、全站备注、状态、最近快照。 |
| `onchain_wallet_chains` | 每个地址启用的链。 |
| `onchain_wallet_requests` | 用户提交的地址申请。 |
| `onchain_user_wallet_subscriptions` | 用户订阅地址。 |
| `onchain_user_wallet_notes` | 用户私有备注。 |
| `onchain_tokens` | token identity、链、合约、symbol、风险状态。 |
| `onchain_balance_snapshots` | 每次抓取 raw 持仓快照，包含被过滤记录。 |
| `onchain_daily_wallet_token_views` | 地址 x token x 上海自然日视图。 |
| `onchain_daily_token_views` | token 日级聚合视图。 |
| `onchain_fetch_runs` | 抓取运行记录。 |
| `onchain_fetch_run_items` | 单地址单链运行状态。 |
| `onchain_token_filter_rules` | 稳定币、主流资产、风险或自定义过滤规则。 |

主要 RPC：

| RPC | 用途 |
| --- | --- |
| `list_onchain_wallets(text, integer)` | 地址库。 |
| `submit_onchain_wallet(text, text[])` | 普通用户提交地址。 |
| `set_onchain_wallet_subscription(uuid, boolean)` | 订阅或取消订阅。 |
| `set_onchain_wallet_note(uuid, text)` | 用户私有备注。 |
| `approve_onchain_wallet_request(uuid)` / `reject_onchain_wallet_request(uuid)` | 管理员审批。 |
| `admin_update_onchain_wallet(uuid, text, text[], text)` | 管理员备注、链配置和状态。 |
| `enqueue_onchain_fetch()` | 管理页手动入队一次抓取。 |
| `get_onchain_token_matrix(text, text[])` | 按代币矩阵。 |
| `get_onchain_wallet_matrix(uuid, text, text[])` | 单地址矩阵。 |
| `get_onchain_overview()` | 总览。 |
| `list_onchain_admin_dashboard()` | 管理页。 |

RLS 口径：

- 匿名用户只能通过 RPC 看轻量预览。
- 普通用户只能读自己的订阅和私有备注。
- 管理员可管理全部。

## 种子地址

Migration 会写入两个已审批生产种子地址：

| 地址 | 全站备注 | 启用链 |
| --- | --- | --- |
| `0xa7bfa56d1fbb7809b8424b452896707be408e1bc` | `恰米` | BSC |
| `0xa05ec35f7d1eba823cff2ed26aeaed419683742f` | `裤子` | BSC、Ethereum、Base |

## 后端命令

从仓库根目录运行：

```bash
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-onchain-doctor
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-onchain-fetch --once
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-onchain-rebuild-daily --days 30
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-onchain-process-pending --limit 1
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-api --host 127.0.0.1 --port 8010
```

`public-worker` 长驻进程已集成链上调度：

- 按 `PUBLIC_ONCHAIN_FETCH_TIMES` 直接执行 scheduled 抓取。
- 每个 poll 周期处理一个 `enqueue_onchain_fetch()` 创建的 pending run。
- `public-worker-doctor` 会额外输出 OKX key 是否存在、onchain 地址数和最近抓取状态。

## 抓取状态

单地址单链状态：

| 状态 | 含义 |
| --- | --- |
| `success` | API 成功返回并有可见持仓。 |
| `empty` | API 成功返回，但过滤后没有大于阈值的可见持仓。 |
| `api_error` | OKX 返回错误。 |
| `rate_limited` | OKX 限流。 |
| `auth_error` | OKX 鉴权或区域权限错误。 |
| `network_error` | 网络或代理错误。 |
| `partial` | 保留给后续多链批量请求。 |

失败不能展示成 0。页面和管理页都必须展示最近运行状态和错误样本。

## 本地验证

```bash
/mnt/d/Software/Code/Anaconda/python.exe -m pytest tests/test_onchain.py -q
/mnt/d/Software/Code/Anaconda/python.exe -m compileall backend/packages backend/src

cd public-web
npm run lint
npm run build
```

前端本地启动后验证：

```bash
cd public-web
npm run dev
```

页面：

- `/onchain`
- `/onchain/wallets`
- `/onchain/tokens`
- `/onchain/gmgn-labels`
- `/onchain/admin`

关键检查：

- 恰米只启用 BSC。
- 裤子启用 BSC、Ethereum、Base。
- 地址不会以完整长串撑开 UI。
- 链筛选、指标切换、私有备注和管理页保存可用。
- GMGN 备注生成请求体不包含用户粘贴的 EVM/Solana 原备注。

## 部署验证

执行 migration：

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os
from pathlib import Path
import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)
dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

sql_path = Path("supabase/migrations/018_onchain_ambush.sql")
with psycopg.connect(dsn, autocommit=False) as conn:
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"))
    conn.commit()

print(f"migration=applied file={sql_path}")
PY
```

验证种子、过滤规则和数据行：

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os
import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)
dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

queries = {
    "wallets": "select count(*) from public.onchain_wallets",
    "wallet_chains": "select count(*) from public.onchain_wallet_chains where enabled",
    "filter_rules": "select count(*) from public.onchain_token_filter_rules where enabled",
    "runs": "select count(*) from public.onchain_fetch_runs",
    "snapshots": "select count(*) from public.onchain_balance_snapshots",
    "daily_wallet": "select count(*) from public.onchain_daily_wallet_token_views",
    "daily_token": "select count(*) from public.onchain_daily_token_views",
}

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        for label, sql in queries.items():
            cur.execute(sql)
            print(f"{label}={cur.fetchone()[0]}")
PY
```

Linux 部署时按 `docs/agent-operations-runbook.md`：先看服务器 `git status --short`，不要覆盖脏改；重启 `jibai-public-worker.service` 或 `jibai-public-api.service` 后必须读最新 `journalctl`，不能只看 `active`。

## 2026-05-20 补充

- `/onchain/tokens` 不再单独提供“持有人数”展示模式，只保留“数量”和“金额”两种主口径。
- 在“数量”和“金额”模式下，单元格会显示为 `主值（人数）`，括号里的数字表示当天持有该代币的地址数。
- 页面支持按持有人数、数量、金额做升序或降序排序；排序口径按当前表格最右侧日期对应的值计算。
