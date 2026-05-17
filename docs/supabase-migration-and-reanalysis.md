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

For another migration, change only `sql_path`.

## Run Recent Reanalysis Locally

The public reanalysis command now runs locally as long as `.env` has
`SUPABASE_DB_URL` and AI credentials.

For the current 30-day public history window:

```bash
AI_API_TIMEOUT_SECONDS=90 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-reanalyze-recent --days 30 --clear-analysis
```

What it does:

- keeps raw `content_items`
- clears analysis/materialized outputs
- reanalyzes recent X content using current prompt and parser logic
- rebuilds author daily summaries and stock daily views
- leaves `theme_daily_views` empty for the stock-signal-only product

If only a few notes failed or timed out, do not clear again. Rebuild timelines
and fill missing analyses:

```bash
AI_API_TIMEOUT_SECONDS=180 \
/mnt/d/Software/Code/Anaconda/python.exe backend/src/main.py public-rebuild-timelines
```

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
            "theme_daily_views",
        ]:
            cur.execute(f"select count(*) from {table}")
            print(f"{table}={cur.fetchone()[0]}")

        cur.execute("""
            select entity_type, signal_type, direction, judgment_type, count(*)
            from content_viewpoints
            group by 1,2,3,4
            order by 5 desc
        """)
        print("viewpoint_distribution=" + repr(cur.fetchall()))

        cur.execute("""
            select count(*)
            from content_viewpoints
            where entity_type <> 'stock'
               or signal_type not in ('explicit_stance', 'logic_based')
               or direction not in ('positive', 'negative')
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
PY
```

Anonymous RPC results may be limited by the function's preview rules. The
important checks are:

- stock RPC returns successfully
- theme entity list is empty
- theme timeline is `null`

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
- adds `get_visible_stock_matrix(end_date_arg text)` for the 7-day stock x
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
