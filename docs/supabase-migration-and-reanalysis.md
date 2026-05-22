# Local Supabase Migration And Reanalysis Runbook

This document is local-only and ignored by Git. It records how another local
Codex session can run Supabase migrations and public-content reanalysis from
this checkout without SSHing into the Linux server.

## Principle

Run the operation from the local repository with local Python.

Required local secrets live in `.env`:

```env
SUPABASE_DB_URL='postgresql://...'
OPENAI_API_KEY='...'
OPENAI_BASE_URL='https://.../v1'
```

`SUPABASE_DB_URL` is the important part for SQL. `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` are not enough for arbitrary SQL migrations because
they are REST/API credentials, not a Postgres connection string.

Never print the actual DSN or API keys in chat, logs, docs, commits, or command
output. Only print whether a variable is present.

## Local Python Runtime

On this machine, the Windows Anaconda Python has the backend dependencies:

```bash
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py --help
```

If using another Python, it needs at least:

```bash
pip install psycopg python-dotenv
```

The backend also uses LiteLLM/OpenAI-compatible packages for reanalysis. If the
command import fails, install the project backend dependencies in that runtime.

## Preflight

Run from repo root:

```bash
python3 - <<'PY'
from pathlib import Path

env_path = Path(".env")
keys = {}
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        keys[key.strip()] = bool(value.strip().strip("'\""))

for key in [
    "SUPABASE_DB_URL",
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "AI_API_KEY",
    "OPENAI_BASE_URL",
    "AI_BASE_URL",
]:
    print(f"{key}=" + ("set" if keys.get(key) else "missing"))
PY
```

Check Python imports without printing secrets:

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
for module in ["psycopg", "dotenv", "litellm"]:
    try:
        __import__(module)
        print(f"{module}=ok")
    except Exception as exc:
        print(f"{module}=missing:{type(exc).__name__}")
PY
```

Compile changed backend code before touching the DB:

```bash
python3 -m compileall backend/packages backend/src
```

If WSL Python is missing dependencies, use:

```bash
/mnt/d/Software/Code/Anaconda/python.exe -m compileall backend/packages backend/src
```

## Apply A Supabase Migration Locally

Use local `.env`, local Python, and a SQL migration file:

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

sql_path = Path("supabase/migrations/011_stock_signal_only_views.sql")
sql = sql_path.read_text(encoding="utf-8")

with psycopg.connect(dsn, autocommit=False) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

print(f"migration=applied file={sql_path}")
PY
```

For the stock/crypto domain split, use:

```python
sql_path = Path("supabase/migrations/015_crypto_domain.sql")
```

If account submission fails with
`column reference "account_id" is ambiguous` after the domain split, apply:

```python
sql_path = Path("supabase/migrations/017_fix_submit_x_account_conflict_target.sql")
```

For the public stock narrative brief, use:

```python
sql_path = Path("supabase/migrations/019_stock_narrative_briefs.sql")
```

For crypto asset-candidate filtering and provisional normalization metadata,
use:

```python
sql_path = Path("supabase/migrations/022_crypto_asset_candidate_rpc.sql")
```

For crypto asset narrative briefs and the crypto overview summary column, use:

```python
sql_path = Path("supabase/migrations/023_crypto_asset_narrative_briefs.sql")
```

For crypto blocked terms and admin asset deletion controls, use:

```python
sql_path = Path("supabase/migrations/024_crypto_admin_controls.sql")
```

For crypto matrix filtering parity and brief `identity_status`, use:

```python
sql_path = Path("supabase/migrations/025_crypto_matrix_identity_filters.sql")
```

For another migration, change only `sql_path`.

## Run Recent Reanalysis Locally

The public reanalysis command now runs locally as long as `.env` has
`SUPABASE_DB_URL` and AI credentials.

For the current 30-day public stock history window:

```bash
AI_API_TIMEOUT_SECONDS=90 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-reanalyze-recent --days 30 --clear-analysis
```

For crypto, keep the domain explicit:

```bash
AI_API_TIMEOUT_SECONDS=90 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-reanalyze-recent --domain crypto --days 30 --clear-analysis
```

What it does:

- keeps raw `content_items`
- clears analysis/materialized outputs
- reanalyzes recent X content using current prompt and parser logic
- rebuilds author daily summaries and stock or crypto daily views for the selected domain
- for stock, refreshes lightweight stock market data and leaves `theme_daily_views` empty for the stock-signal-only product
- for crypto, writes no market data or K-line cache

If only a few notes failed or timed out, do not clear again. Rebuild timelines
and fill missing analyses:

```bash
AI_API_TIMEOUT_SECONDS=180 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-rebuild-timelines
```

Crypto timeline rebuild and alias normalization:

```bash
AI_API_TIMEOUT_SECONDS=180 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-rebuild-timelines --domain crypto

AI_API_TIMEOUT_SECONDS=180 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py normalize-crypto-assets --days 30
```

After changing crypto resolver logic, prefer `normalize-crypto-assets --days 30`
over another full LLM reanalysis when the existing `content_analyses` rows are
already present. It re-normalizes stored crypto viewpoints, filters
`asset_candidate=false` rows out of materialized asset timelines, and rebuilds
`crypto_entity_daily_views` from current code.

Generate or refresh the public stock narrative brief after the migration:

```bash
AI_API_TIMEOUT_SECONDS=180 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-generate-stock-narrative
```

Use `--date YYYY-MM-DD --force` only when intentionally replacing an existing
successful brief for that date.

Generate or refresh crypto asset briefs after the crypto migration or resolver
change:

```bash
AI_API_TIMEOUT_SECONDS=180 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-generate-crypto-asset-briefs
```

Useful one-off variants:

```bash
AI_API_TIMEOUT_SECONDS=180 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-generate-crypto-asset-briefs --asset-key orbiter --force

AI_API_TIMEOUT_SECONDS=180 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-generate-crypto-asset-briefs --asset-key aeon --asset-key pitch --asset-key surplus --force

AI_API_TIMEOUT_SECONDS=180 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-generate-crypto-asset-briefs --days 30 --limit 20
```

What it does:

- reads recent visible crypto assets from `crypto_entity_daily_views`
- reuses existing CA identifiers from `crypto_entities` when present
- otherwise calls OKX Onchain OS token search for up to five CA candidates
- searches X for both the name-group and each CA-group
- uses cheap overlap plus `gpt-5.4-mini` similarity judgment to decide whether a CA candidate is the same project
- stores one frozen summary row per `asset_key` in `crypto_asset_narrative_briefs`
- stores `identity_status` as `anchored`, `fuzzy`, or `ambiguous`
- leaves `contract_address` empty and `ca_resolution_status='unresolved'` when no candidate passes, while still allowing a name-only summary

The brief X search runtime is now backend-internal and browser-only. Server or
local runtimes must have both Python package dependencies and Playwright
Chromium installed. This pipeline must not depend on `Reference/` scripts.

## Verify Database State Locally

Run this after migration or reanalysis:

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os

import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)
dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        for table in [
            "content_analyses",
            "content_viewpoints",
            "security_mentions",
            "author_daily_summaries",
            "security_daily_views",
            "crypto_entities",
            "crypto_entity_daily_views",
            "crypto_asset_narrative_briefs",
            "theme_daily_views",
            "stock_narrative_briefs",
        ]:
            cur.execute(f"select count(*) from {table}")
            print(f"{table}={cur.fetchone()[0]}")

        cur.execute("""
            select analysis_domain, entity_type, signal_type, direction, judgment_type, count(*)
            from content_viewpoints
            group by 1,2,3,4,5
            order by 6 desc
        """)
        print("viewpoint_distribution=" + repr(cur.fetchall()))

        cur.execute("select public.get_latest_stock_narrative_brief()")
        brief = cur.fetchone()[0]
        print("stock_narrative_latest=" + repr({
            "brief_date": brief.get("brief_date"),
            "window_start": brief.get("window_start"),
            "window_end": brief.get("window_end"),
            "has_text": bool(brief.get("brief_text")),
        }))

        cur.execute("""
            select count(*)
            from content_viewpoints
            where analysis_domain = 'stock'
              and (
                entity_type <> 'stock'
                or signal_type not in ('explicit_stance', 'logic_based')
                or direction not in ('positive', 'negative')
              )
        """)
        print("invalid_viewpoints=" + str(cur.fetchone()[0]))

        cur.execute("""
            select count(*)
            from security_mentions
            where signal_type not in ('explicit_stance', 'logic_based')
               or direction not in ('positive', 'negative')
        """)
        print("invalid_mentions=" + str(cur.fetchone()[0]))

        cur.execute("select min(date_key), max(date_key), count(*) from author_daily_summaries")
        print("author_dates=" + repr(cur.fetchone()))

        cur.execute("select min(date_key), max(date_key), count(*) from security_daily_views")
        print("stock_dates=" + repr(cur.fetchone()))

        cur.execute("select min(date_key), max(date_key), count(*) from crypto_entity_daily_views")
        print("crypto_dates=" + repr(cur.fetchone()))

        cur.execute("""
            select status, identity_status, ca_resolution_status, count(*)
            from crypto_asset_narrative_briefs
            group by 1,2,3
            order by 1,2,3
        """)
        print("crypto_brief_statuses=" + repr(cur.fetchall()))

        cur.execute("""
            select asset_key, left(summary_text, 80), contract_address, model_name
            from crypto_asset_narrative_briefs
            order by updated_at desc
            limit 5
        """)
        print("crypto_brief_samples=" + repr(cur.fetchall()))
PY
```

Expected stock-signal-only state:

- `content_viewpoints.entity_type` only `stock`
- `signal_type` only `explicit_stance` or `logic_based`
- `direction` only `positive` or `negative`
- `invalid_viewpoints=0`
- `invalid_mentions=0`
- `theme_daily_views=0`
- date range matches the intended Asia/Shanghai natural-day window

Expected crypto state after a crypto run:

- `content_analyses` can contain both `analysis_domain='stock'` and `analysis_domain='crypto'` for the same `content_id`
- crypto rows in `content_viewpoints` use `analysis_domain='crypto'` and `entity_type='crypto_entity'`
- weak signals may have `signal_type in ('informational','mention_signal')` and `direction='unknown'`
- `crypto_entity_daily_views` is populated when crypto signals exist
- `crypto_asset_narrative_briefs` stores one row per `asset_key`
- successful brief rows should normally use `model_name='gpt-5.4-mini'`
- `ca_resolution_status` may be `existing_identifier`, `resolved`, or `unresolved`
- `identity_status` may be `anchored`, `fuzzy`, or `ambiguous`

## Verify RPC Behavior Locally

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os

import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)
dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("select count(*) from public.list_visible_entities('stock','',100,'date_desc')")
        print("rpc_stock_count=" + str(cur.fetchone()[0]))
        cur.execute("select count(*) from public.list_visible_entities('theme','',100,'date_desc')")
        print("rpc_theme_count=" + str(cur.fetchone()[0]))
        cur.execute("select public.get_visible_entity_timeline('theme','anything',1,20) is null")
        print("rpc_theme_timeline_is_null=" + str(cur.fetchone()[0]))
        cur.execute("select count(*) from public.list_visible_crypto_entities('',100,'date_desc')")
        print("rpc_crypto_count=" + str(cur.fetchone()[0]))
        cur.execute("select jsonb_typeof(public.get_visible_crypto_matrix(null))")
        print("rpc_crypto_matrix_type=" + str(cur.fetchone()[0]))
        cur.execute("select count(*) from public.list_visible_crypto_entities('base',100,'date_desc')")
        print("rpc_crypto_base_count=" + str(cur.fetchone()[0]))
        cur.execute("select public.get_visible_crypto_entity_timeline('base',1,20) is null")
        print("rpc_crypto_base_timeline_is_null=" + str(cur.fetchone()[0]))
        cur.execute("select public.get_visible_crypto_matrix(null, 'week')")
        payload = cur.fetchone()[0]
        assets = payload.get("assets") or []
        base_assets = [item for item in assets if item.get("asset_key") == "base"]
        print("rpc_crypto_matrix_base_assets=" + str(len(base_assets)))
        print("rpc_crypto_matrix_identity_keys=" + repr(sorted({key for item in assets[:5] for key in item.keys() if key in ('summary_status', 'identity_status')})))
PY
```

Anonymous RPC results may be limited by the function's preview rules. The
important checks are:

- stock RPC returns successfully
- theme entity list is empty
- theme timeline is `null`
- crypto RPCs return successfully after migration 015, even if there is no crypto data yet
- blocklisted or admin-deleted assets such as `base` stay hidden from crypto list, detail, and matrix RPCs
- matrix asset payload includes both `summary_status` and `identity_status`
- `submit_x_account(..., domain_arg)` can insert or update a domain-scoped request after migration 017

## Restore Author Timeline History Window

`supabase/migrations/013_restore_author_timeline_history_window.sql` fixes the
author list and author timeline RPCs after the stock-signal-only migration
limited visible author days to the latest three Shanghai natural days. The RPCs
still filter to valid stock signals, but they no longer apply a hard three-day
date filter; the visible history is determined by the materialized
`author_daily_summaries` rows.

Rebuild with:

```bash
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-reanalyze-recent --days 30 --clear-analysis
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-refresh-market-data --days 180
```

Afterward, verify that `author_daily_summaries` spans the intended 30-day
content window and `security_daily_prices` spans the intended 180-day K-line
cache window.

## Restore Stock Detail History And Add Matrix Overview

`supabase/migrations/014_stock_detail_sort_and_matrix_overview.sql` updates the
stock-side public RPCs after the same stock-signal-only migration left a hard
three-day date filter in `list_visible_entities` and
`get_visible_entity_timeline`.

The migration:

- keeps stock-only signal filtering
- removes the fixed recent-day cutoff from stock list/detail RPCs
- adds server-side sort support for `date_desc`, `date_asc`, `count_desc`, and
  `count_asc`
- adds the initial `get_visible_stock_matrix(end_date_arg text)` weekly stock x
  author overview table; authenticated users are scoped to subscribed authors,
  while anonymous users keep the public preview scope

Verification after applying it:

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os
import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)
dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("""
        select
          pg_get_functiondef('public.list_visible_entities(text,text,integer,text)'::regprocedure)
            like '%date_key >= ((now() at time zone%' as list_has_cutoff,
          pg_get_functiondef('public.get_visible_entity_timeline(text,text,integer,integer)'::regprocedure)
            like '%date_key >= ((now() at time zone%' as detail_has_cutoff
        """)
        print("stock_rpc_cutoffs=" + repr(cur.fetchone()))

        for sort in ["date_desc", "date_asc", "count_desc", "count_asc"]:
            cur.execute(
                "select array_agg(entity_key order by rn) from ("
                "select entity_key, row_number() over () rn "
                "from public.list_visible_entities('stock','',10,%s)"
                ") s",
                (sort,),
            )
            print(f"sort_{sort}=" + repr(cur.fetchone()[0]))

        cur.execute("select public.get_visible_stock_matrix(null)")
        payload = cur.fetchone()[0]
        print("matrix_window=" + repr((payload.get("start_date"), payload.get("end_date"))))
        print("matrix_counts=" + repr((len(payload.get("stocks") or []), len(payload.get("authors") or []), len(payload.get("cells") or []))))
PY
```

## Frontend Verification

After public-web changes:

```bash
cd public-web
npm run lint
npm run build
```

The production build route list should not include `/themes`.

## Add Stock Matrix Day View

`supabase/migrations/020_stock_matrix_day_granularity.sql` extends the stock
overview matrix RPC so `/stocks/overview` can switch between weekly and daily
windows without changing the visibility rules.

The migration:

- keeps the existing anonymous preview and authenticated subscription scoping
- adds `get_visible_stock_matrix(end_date_arg text, granularity_arg text)` for
  `day` and `week` windows
- keeps the one-argument `get_visible_stock_matrix(end_date_arg text)` wrapper
  so existing callers still get the weekly view
- returns only authors, stocks, and cells that have valid viewpoints inside the
  selected window

Verification after applying it:

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os
import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)
dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("select public.get_visible_stock_matrix(null, 'week')")
        weekly = cur.fetchone()[0]
        print("weekly_window=" + repr((weekly.get("start_date"), weekly.get("end_date"))))
        print("weekly_counts=" + repr((len(weekly.get("stocks") or []), len(weekly.get("authors") or []), len(weekly.get("cells") or []))))

        cur.execute("select public.get_visible_stock_matrix(null, 'day')")
        daily = cur.fetchone()[0]
        print("daily_window=" + repr((daily.get("start_date"), daily.get("end_date"))))
        print("daily_counts=" + repr((len(daily.get("stocks") or []), len(daily.get("authors") or []), len(daily.get("cells") or []))))
PY
```

## Add Crypto Matrix Day View

`supabase/migrations/021_crypto_matrix_day_granularity.sql` extends the crypto
overview matrix RPC so `/crypto/assets/overview` can switch between weekly and
daily windows without changing the existing preview and subscription scoping.

The migration:

- adds `get_visible_crypto_matrix(end_date_arg text, granularity_arg text)` for
  `day` and `week` windows
- keeps the one-argument `get_visible_crypto_matrix(end_date_arg text)` wrapper
  so existing callers still get the weekly view
- returns only authors, assets, and cells that have signal rows inside the
  selected window

Verification after applying it:

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os
import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)
dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("select public.get_visible_crypto_matrix(null, 'week')")
        weekly = cur.fetchone()[0]
        print("crypto_weekly_window=" + repr((weekly.get("start_date"), weekly.get("end_date"))))
        print("crypto_weekly_counts=" + repr((len(weekly.get("assets") or []), len(weekly.get("authors") or []), len(weekly.get("cells") or []))))

        cur.execute("select public.get_visible_crypto_matrix(null, 'day')")
        daily = cur.fetchone()[0]
        print("crypto_daily_window=" + repr((daily.get("start_date"), daily.get("end_date"))))
        print("crypto_daily_counts=" + repr((len(daily.get("assets") or []), len(daily.get("authors") or []), len(daily.get("cells") or []))))
PY
```

## Apply Onchain Ambush Migration

`supabase/migrations/018_onchain_ambush.sql` adds the chain-tracking tables,
RPCs, RLS policies, filter rules, and two approved seed wallets:

- `0xa7bfa56d1fbb7809b8424b452896707be408e1bc` / `恰米` / BSC.
- `0xa05ec35f7d1eba823cff2ed26aeaed419683742f` / `裤子` / BSC, Ethereum, Base.

Apply it locally with the Postgres DSN from `.env`:

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

Then run one fetch and rebuild:

```bash
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-onchain-doctor
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-onchain-fetch --once
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-onchain-rebuild-daily --days 30
```

Verify without printing secrets:

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os
import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)
dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        for table in [
            "onchain_wallets",
            "onchain_wallet_chains",
            "onchain_token_filter_rules",
            "onchain_fetch_runs",
            "onchain_fetch_run_items",
            "onchain_balance_snapshots",
            "onchain_daily_wallet_token_views",
            "onchain_daily_token_views",
        ]:
            cur.execute(f"select count(*) from public.{table}")
            print(f"{table}={cur.fetchone()[0]}")
PY
```

## Optional Server Follow-Up

Local SQL/reanalysis updates Supabase directly. The Linux worker does not need
to run the migration. If backend worker code was also changed and deployed to
GitHub/server, restart and check the worker separately.

Do not treat `systemctl active` alone as proof. Check latest logs for
`database_ok` and the startup line:

```bash
ssh root@47.76.243.147 \
  "systemctl status jibai-public-worker.service --no-pager -l && journalctl -u jibai-public-worker.service -n 50 --no-pager"
```

## Notes From The 2026-05-12 Stock-Signal Migration

The first time this migration was run, SQL was executed on the Linux server
because local `.env` did not yet have `SUPABASE_DB_URL`. After adding
`SUPABASE_DB_URL` locally, future sessions should use this local runbook.

The verified reanalysis window was `2026-05-10` through `2026-05-12` by
Asia/Shanghai natural day. Final verified state included:

- `content_analyses=213`
- `content_viewpoints=127`
- `security_mentions=127`
- `author_daily_summaries=43`
- `security_daily_views=95`
- `theme_daily_views=0`
- invalid stock-signal rows: `0`

## Notes From The 2026-05-21 Crypto Resolver Migration

Migration `022_crypto_asset_candidate_rpc.sql` keeps generic/theme-like crypto
mentions out of visible asset RPCs and exposes the newer crypto matrix payload
fields used by the frontend, including raw identifiers, normalization status,
resolver strategy, match confidence, source signal level, and metadata.

The historical repair used the local venv runtime on Windows:

```powershell
$env:PYTHONPATH='backend'
$env:AI_API_TIMEOUT_SECONDS='180'
.\.venv-codex\Scripts\python.exe backend\src\main.py public-reanalyze-recent --domain crypto --days 30 --clear-analysis
.\.venv-codex\Scripts\python.exe backend\src\main.py normalize-crypto-assets --days 30
```

The second command is important when old materialized rows were created before
the resolver/filter logic changed. It clears and rebuilds
`crypto_entity_daily_views` for the selected crypto window from the current
stored analyses.

Verified state for the `2026-04-22` through `2026-05-21` Asia/Shanghai crypto
window after the rebuild:

- crypto domain notes in worker scope: `336`
- missing crypto analyses in scope: `0`
- crypto viewpoints in scope: `598`
- crypto author daily summaries: `49`
- crypto entity daily views: `226`
- `AEON` symbol and meme-ticker rows materialized under `tick:aeon`
- `decentralized LLM` no longer appears in visible crypto entities or materialized crypto daily views
- `1confirmation` mentions normalize to `proj:1confirmation`, but are not materialized as an asset when classified as `org_or_fund` with `asset_candidate=false`
