# Public Supabase Worker

Public web uses Supabase as the primary database. Vercel only serves `public-web/`; Alibaba Cloud runs this Python worker for X crawling and AI analysis.

## What It Does

- Polls `crawl_jobs` every 30 seconds.
- Enqueues scheduled crawl jobs at `04:00,10:00,16:00,22:00` Asia/Shanghai.
- Processes only one crawl job at a time with a Postgres advisory lock.
- Crawls X accounts serially with a 5 second account delay.
- Runs AI analysis and writes summaries, viewpoints, stocks, and themes back to Supabase.
- Refreshes daily market-data cache for stocks mentioned in the current run. Plain
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
PUBLIC_WORKER_NITTER_INSTANCES=xcancel.com,nitter.tiekoetter.com,nitter.catsarch.com
PUBLIC_WORKER_MARKET_DATA_MAX_SECURITIES=30
PUBLIC_WORKER_MARKET_DATA_DAYS=730
PUBLIC_WORKER_MARKET_DATA_DELAY_SECONDS=0.25
```

Use the Supabase Postgres connection string, not the anon key. The anon key is for browser/database API access; this worker needs a server-side SQL connection so it can claim jobs, run locks, and write analysis tables.

AI settings continue to use the existing backend configuration files and environment variables.

`PUBLIC_WORKER_NITTER_INSTANCES` is optional. Public Nitter mirrors often add bot protection or go offline, so keep this value configurable on the server instead of relying on the code defaults. Use comma-separated host names without `https://`.

Market-data settings are optional. The defaults refresh at most 30 stocks per
analysis run, cache roughly two years of daily candles, and wait 0.25 seconds
between symbols. Market-data failures are isolated from the crawl and AI
pipeline; the job result records `market_errors=N`.

## Commands

```bash
cd /opt/Jibai
source .venv/bin/activate
set -a
source /etc/jibai/public-worker.env
set +a

python backend/src/main.py public-worker --once
python backend/src/main.py public-worker
python backend/src/main.py public-enqueue-scheduled
python backend/src/main.py public-refresh-market-data --query AMD --limit 1
python backend/src/main.py public-import-sqlite
```

`public-worker --once` processes at most one pending job and exits. Use it for
manual tests after migrations or deploys. `public-worker` starts the long-running
poller and in-process scheduler. `public-enqueue-scheduled` inserts one scheduled
crawl job immediately, which is useful when you want the worker to process a run
without waiting for the next configured wall-clock time.

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
