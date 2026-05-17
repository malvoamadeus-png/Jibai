# Public Supabase Worker

Public web uses Supabase as the primary database. Vercel only serves `public-web/`; Alibaba Cloud runs this Python worker for X crawling and AI analysis.

## What It Does

- Polls `crawl_jobs` every 30 seconds.
- Enqueues scheduled crawl jobs at `04:00,10:00,16:00,22:00` Asia/Shanghai.
- Processes only one crawl job at a time with a Postgres advisory lock.
- Crawls X accounts serially with a 5 second account delay.
- Runs stock-only AI signal analysis and writes author summaries, stock viewpoints, and stock timelines back to Supabase.
- Initial backfills refresh the 180-day market-data cache. Scheduled crawls use
  a lightweight refresh for stocks newly analyzed in that run. Plain
  tickers such as `NVDA`, `AAPL`, and `TSLA` use Yahoo Finance. A-share markets
  `SSE`, `SZSE`, and `BJSE` still use EastMoney.

Approval flow:

- Admin approves a pending account in `public-web`.
- Supabase creates one `initial_backfill` job for that account.
- Worker backfills up to 30 posts from the last 30 days, skipping pinned posts older than 30 days.
- Later scheduled/manual jobs crawl approved accounts that have at least one subscriber.

## Environment

Create `/etc/jibai/public-worker.env` on the server:

```bash
SUPABASE_DB_URL='postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require'
PUBLIC_WORKER_CRAWL_TIMES=04:00,10:00,16:00,22:00
PUBLIC_WORKER_ACCOUNT_DELAY_SECONDS=5
PUBLIC_WORKER_POLL_SECONDS=30
PUBLIC_WORKER_HEADLESS=true
PUBLIC_WORKER_PAGE_WAIT_SECONDS=6
PUBLIC_WORKER_NITTER_INSTANCES=nitter.tiekoetter.com,nitter.catsarch.com,xcancel.com
PUBLIC_WORKER_MARKET_DATA_MAX_SECURITIES=30
PUBLIC_WORKER_MARKET_DATA_DAYS=180
PUBLIC_WORKER_LIGHT_MARKET_DATA_MAX_SECURITIES=10
PUBLIC_WORKER_LIGHT_MARKET_DATA_DAYS=7
PUBLIC_WORKER_ANALYSIS_WINDOW_DAYS=30
PUBLIC_WORKER_MARKET_DATA_DELAY_SECONDS=0.25

AI_PROVIDER=openai-compatible
AI_API_KEY='your-openai-compatible-api-key'
AI_BASE_URL='https://your-openai-compatible-endpoint/v1'
AI_MODEL='your-analysis-model'
AI_FALLBACK_MODELS='optional-fallback-model-1,optional-fallback-model-2'
```

Use the Supabase Postgres connection string, not the anon key. The anon key is for browser/database API access; this worker needs a server-side SQL connection so it can claim jobs, run locks, and write analysis tables.

AI settings use the same OpenAI-compatible configuration as the local backend.
If local development uses an OpenAI relay endpoint, copy the same endpoint into
`AI_BASE_URL` and the same relay key into `AI_API_KEY`. Without an AI key, the
worker can still crawl X content and write daily fallback summaries, but it
cannot generate structured stock viewpoints or stock pages from new
content. `public-worker-doctor` prints `api_key_configured=yes/no` so this is
visible during diagnosis.

The X crawler discovers user timelines through FxTwitter's statuses endpoint
first. Nitter is now only a fallback for cases where that API is unavailable.
`PUBLIC_WORKER_NITTER_INSTANCES` is optional. Public Nitter mirrors often add
bot protection or go offline, so keep this value configurable on the server
instead of relying on the code defaults. Use comma-separated host names without
`https://`.

Market-data settings are optional. Backfill and manual market refresh default
to at most 30 stocks and 180 days of daily candles. Scheduled crawls default to
at most 10 newly analyzed stocks and only fetch the latest 7 days of daily
candles, but the K-line cache is still retained for the 180-day
`PUBLIC_WORKER_MARKET_DATA_DAYS` window. Do not use the light refresh window as
the delete/prune window. Scheduled crawls skip market data when the run produced
no new stock analysis. Market-data failures are isolated from the crawl and AI
pipeline; the job result records `market_errors=N`.

Analysis output is intentionally windowed. `PUBLIC_WORKER_ANALYSIS_WINDOW_DAYS`
defaults to `30`, matching the initial backfill lookback and using
Asia/Shanghai natural days. Old raw posts stay in `content_items`; when
analysis tables are cleared and rebuilt, the public timelines should be
rebuilt from this 30-day window rather than only the latest scheduled crawl
window.

Public stock browsing has two RPC-backed surfaces. `/stocks` uses
`list_visible_entities` and `get_visible_entity_timeline` for the detail view;
the stock list supports sorting by latest date or total visible mentions and
must not apply a fixed recent-day cutoff. `/stocks/overview` uses
`get_visible_stock_matrix`, which returns a 7-day stock x author matrix ending
at the latest visible stock-signal date unless a specific `end` date is passed.
For logged-in users the matrix is scoped to subscribed authors, including admin
users; anonymous users keep the public preview scope. Matrix cells keep every
valid positive/negative stock signal as an individual point.

## Commands

```bash
cd /opt/Jibai
source .venv/bin/activate
set -a
source /etc/jibai/public-worker.env
set +a

python backend/src/main.py public-worker --once
python backend/src/main.py public-worker
python backend/src/main.py public-worker-doctor
python backend/src/main.py public-enqueue-scheduled
python backend/src/main.py public-reanalyze-recent --days 30 --clear-analysis
python backend/src/main.py public-refresh-market-data --query AMD --limit 1
python backend/src/main.py public-import-sqlite
```

`public-worker --once` processes at most one pending job and exits. Use it for
manual tests after migrations or deploys. `public-worker` starts the long-running
poller and in-process scheduler. `public-enqueue-scheduled` inserts one scheduled
crawl job immediately, which is useful when you want the worker to process a run
without waiting for the next configured wall-clock time.

`public-reanalyze-recent --days 30 --clear-analysis` keeps raw `content_items`,
clears analysis/materialized outputs, and force-runs the current stock-only
signal extraction over the latest thirty Asia/Shanghai natural days.

`public-worker-doctor` is read-only. Run it on the server with the same
environment file as the worker to print queue counts, due pending jobs, running
job age, latest scheduled job, account/subscription counts, and whether a job is
holding the Postgres worker lock at that instant.

The long-running `public-worker` validates the database connection before it
starts APScheduler. If the service exits immediately, inspect the service
environment first; for example, a missing newline in the env file can append the
next variable name to the Postgres database name.

`public-refresh-market-data` refreshes the K-line cache without crawling X or
running AI. Use it to backfill one ticker immediately after deploys or when a
stock page says market data is unavailable:

```bash
python backend/src/main.py public-refresh-market-data --query AMD --limit 1
python backend/src/main.py public-refresh-market-data --key amd --limit 1
```

The command prints the matched `security_key` values before fetching. If
`--query AMD` does not match `amd`, inspect `security_entities` because the
AI/entity normalization probably stored the object under a company-name key
without a ticker.

Before the market-data path can return K-line data to `public-web`, apply the
Supabase migrations through `supabase/migrations/004_public_read_rpc.sql` and
`supabase/migrations/005_stock_daily_prices.sql`.

## Smoke Tests

Backend-only checks that do not need Supabase credentials:

```bash
cd /opt/Jibai
source .venv/bin/activate
python -m compileall backend/packages backend/src
PYTHONPATH=backend python - <<'PY'
from packages.common.market_data import build_market_data_target, fetch_security_daily

for ticker in ["NVDA", "AAPL", "TSLA"]:
    payload = fetch_security_daily(ticker=ticker, market=None, security_key=ticker.lower(), days=30)
    print(ticker, len(payload.get("candles") or []), payload.get("sourceLabel"), payload.get("message"))

print(build_market_data_target(ticker="300502", market="SZSE", security_key="300502"))
PY
```

Supabase integration check:

```bash
cd /opt/Jibai
source .venv/bin/activate
set -a
source /etc/jibai/public-worker.env
set +a

python backend/src/main.py public-enqueue-scheduled
python backend/src/main.py public-worker --once
```

After a successful run, the admin job result should include
`market_prices=... market_errors=...`. If at least one subscribed X account has
stock viewpoints with a supported ticker, `security_daily_prices` should contain
daily candles and `/stocks` should render the K-line chart for logged-in users.

## systemd

Create `/etc/systemd/system/jibai-public-worker.service`:

```ini
[Unit]
Description=Jibai public Supabase worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/Jibai
EnvironmentFile=/etc/jibai/public-worker.env
ExecStart=/opt/Jibai/.venv/bin/python backend/src/main.py public-worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then run:

```bash
systemctl daemon-reload
systemctl enable --now jibai-public-worker
systemctl status jibai-public-worker
journalctl -u jibai-public-worker -f
```
