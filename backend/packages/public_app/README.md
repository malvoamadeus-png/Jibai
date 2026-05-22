# Public Supabase Worker

Public web uses Supabase as the primary database. Vercel only serves `public-web/`; Alibaba Cloud runs this Python worker for X crawling and AI analysis.

## What It Does

- Polls `crawl_jobs` every 30 seconds.
- Enqueues scheduled crawl jobs at `04:00,10:00,16:00,22:00` Asia/Shanghai.
- Fetches approved onchain wallet holdings at
  `04:20,10:20,16:20,22:20` Asia/Shanghai by default.
- Processes only one crawl job at a time with a Postgres advisory lock.
- Crawls X accounts serially with a 5 second account delay.
- Runs stock or crypto AI signal analysis by job domain and writes author summaries, viewpoints, and materialized timelines back to Supabase.
- Reuses `content_items` for raw X content so one X post is fetched once, while `content_analyses.analysis_domain` can store separate stock and crypto results for the same post.
- Initial backfills refresh the 180-day market-data cache. Scheduled crawls use
  a lightweight refresh for the most recent stock signals in the analysis
  window, so older-but-visible stock pages still receive latest candles. Plain
  tickers such as `NVDA`, `AAPL`, and `TSLA` use Yahoo Finance. A-share markets
  `SSE`, `SZSE`, and `BJSE` still use EastMoney.
- Crypto jobs do not write market data or K-line cache in the first version.

Approval flow:

- Admin approves a pending account in `public-web`.
- Supabase creates one `initial_backfill` job for that account and domain.
- Worker backfills up to 30 posts from the last 30 days, skipping pinned posts older than 30 days.
- Later scheduled/manual jobs crawl approved accounts in that domain that have at least one subscriber.

## Environment

Create `/etc/jibai/public-worker.env` on the server:

```bash
SUPABASE_URL='https://your-project.supabase.co'
SUPABASE_ANON_KEY='your-supabase-anon-key'
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
PUBLIC_WORKER_DOMAINS=stock,crypto
PUBLIC_WORKER_MARKET_DATA_DELAY_SECONDS=0.25
PUBLIC_WORKER_CRYPTO_ASSET_BRIEF_TIME=22:50
PUBLIC_ONCHAIN_ENABLED=true
PUBLIC_ONCHAIN_FETCH_TIMES=04:20,10:20,16:20,22:20
PUBLIC_ONCHAIN_MIN_VALUE_USD=200

AI_PROVIDER=openai-compatible
AI_API_KEY='your-openai-compatible-api-key'
AI_BASE_URL='https://your-openai-compatible-endpoint/v1'
AI_MODEL='your-analysis-model'
AI_FALLBACK_MODELS='optional-fallback-model-1,optional-fallback-model-2'

OKX_API_KEY='your-okx-web3-api-key'
OKX_SECRET_KEY='your-okx-web3-secret-key'
OKX_PASSPHRASE='your-okx-web3-passphrase'
PUBLIC_API_ALLOWED_ORIGINS='https://your-public-web-domain.com,http://localhost:3000'
```

Use the Supabase Postgres connection string, not the anon key. The anon key is for browser/database API access; this worker needs a server-side SQL connection so it can claim jobs, run locks, and write analysis tables.

The Linux public API also uses `SUPABASE_URL` and `SUPABASE_ANON_KEY` to verify
Supabase access tokens for logged-in users. `PUBLIC_API_ALLOWED_ORIGINS` must
include the Vercel public-web origin so browsers can call the API.

AI settings use the same OpenAI-compatible configuration as the local backend.
If local development uses an OpenAI relay endpoint, copy the same endpoint into
`AI_BASE_URL` and the same relay key into `AI_API_KEY`. Without an AI key, the
worker can still crawl X content and write daily fallback summaries, but it
cannot generate structured stock viewpoints, crypto signals, or stock/crypto
pages from new content. `public-worker-doctor` prints `api_key_configured=yes/no`
so this is visible during diagnosis.

The X crawler discovers user timelines through FxTwitter's statuses endpoint
first. Nitter is now only a fallback for cases where that API is unavailable.
`PUBLIC_WORKER_NITTER_INSTANCES` is optional. Public Nitter mirrors often add
bot protection or go offline, so keep this value configurable on the server
instead of relying on the code defaults. Use comma-separated host names without
`https://`.

Crypto asset brief X search is a separate runtime from timeline crawling. It is
now implemented inside `backend/packages/public_app/x_search.py`, uses
Playwright Chromium in browser-only mode, and must not import or execute
anything from `Reference/`. This brief search path also does not depend on
Nitter.

Market-data settings are optional. Backfill and manual market refresh default
to at most 30 stocks and 180 days of daily candles. Scheduled crawls default to
at most 10 recently visible stocks and only fetch the latest 7 days of daily
candles, but the K-line cache is still retained for the 180-day
`PUBLIC_WORKER_MARKET_DATA_DAYS` window. Do not use the light refresh window as
the delete/prune window. Scheduled crawls skip market data only when the
analysis window has no stock signals. Market-data failures are isolated from
the crawl and AI pipeline; the job result records `market_errors=N`.

Analysis output is intentionally windowed. `PUBLIC_WORKER_ANALYSIS_WINDOW_DAYS`
defaults to `30`, matching the initial backfill lookback and using
Asia/Shanghai natural days. Old raw posts stay in `content_items`; when
analysis tables are cleared and rebuilt, the public timelines should be
rebuilt from this 30-day window rather than only the latest scheduled crawl
window.

Scheduled enqueue uses `PUBLIC_WORKER_DOMAINS`, defaulting to `stock,crypto`.
Each queued job carries `crawl_jobs.domain`. Stock and crypto account approval,
subscription, analysis output, author timelines, and admin lists are isolated
by this domain. The same X account can be approved in both domains; raw content
is shared, but analysis and materialized results are not.

Public stock browsing has two RPC-backed surfaces. `/stocks` uses
`list_visible_entities` and `get_visible_entity_timeline` for the detail view;
the stock list supports sorting by latest date or total visible mentions and
must not apply a fixed recent-day cutoff. `/stocks/overview` uses
`get_visible_stock_matrix`, which returns a 7-day stock x author matrix ending
at the latest visible stock-signal date unless a specific `end` date is passed.
For logged-in users the matrix is scoped to subscribed authors, including admin
users; anonymous users keep the public preview scope. Matrix cells keep every
valid positive/negative stock signal as an individual point.

`/stocks/narrative` uses `get_latest_stock_narrative_brief` and is visible to
anonymous and logged-in users. The brief is generated from all approved stock
domain accounts, not from the current user's subscriptions. The long-running
worker runs this once per day at `PUBLIC_WORKER_STOCK_NARRATIVE_TIME`, default
`22:40` Asia/Shanghai, after the last default scheduled X crawl time.

Public crypto browsing has three RPC-backed surfaces. `/crypto/feed` uses the
domain-aware author RPC and suppresses the author daily summary sentence; cards
only show crypto entity signals. `/crypto/assets` uses
`list_visible_crypto_entities` and `get_visible_crypto_entity_timeline` for the
detail view and never renders K-line data. `/crypto/assets/overview` uses
`get_visible_crypto_matrix`; green dots are positive, red dots are negative,
and gray dots are weak informational or mention signals such as reposts,
announcements, data broadcasts, or plain mentions.

Public onchain browsing uses OKX Web3 from the backend only. The worker reads
`OKX_API_KEY`, `OKX_SECRET_KEY`, and `OKX_PASSPHRASE`; these values must not be
added to `public-web` env. `/onchain` shows overview data, `/onchain/tokens`
shows the token x date matrix, `/onchain/wallets` shows the address library and
single-wallet matrix, and `/onchain/admin` enqueues manual fetch runs. The
long-running worker executes both scheduled fetches and pending manual onchain
runs.

`/onchain/gmgn-labels` calls the Linux public API endpoint
`POST /api/onchain/gmgn-labels`. The API receives only token addresses and
`limit`; user-pasted EVM/Solana GMGN label files stay in the browser and are
used locally for de-duplication.

## Commands

```bash
cd /opt/Jibai
source .venv/bin/activate
set -a
source /etc/jibai/public-worker.env
set +a

python backend/src/main.py public-worker --once
python backend/src/main.py public-worker
python backend/src/main.py public-api --host 127.0.0.1 --port 8010
python backend/src/main.py public-worker-doctor
python backend/src/main.py public-enqueue-scheduled
python backend/src/main.py public-onchain-doctor
python backend/src/main.py public-onchain-fetch --once
python backend/src/main.py public-onchain-process-pending --limit 1
python backend/src/main.py public-onchain-rebuild-daily --days 30
python backend/src/main.py public-reanalyze-recent --days 30 --clear-analysis
python backend/src/main.py public-reanalyze-recent --domain crypto --days 30 --clear-analysis
python backend/src/main.py public-rebuild-timelines --domain crypto
python backend/src/main.py normalize-crypto-assets --days 30
python backend/src/main.py public-refresh-market-data --query AMD --limit 1
python backend/src/main.py public-generate-stock-narrative
python backend/src/main.py public-generate-stock-narrative --date 2026-05-18 --force
python backend/src/main.py public-generate-crypto-asset-briefs
python backend/src/main.py public-generate-crypto-asset-briefs --asset-key orbiter --force
python backend/src/main.py public-import-sqlite
```

`public-worker --once` processes at most one pending job and exits. Use it for
manual tests after migrations or deploys. `public-worker` starts the long-running
poller and in-process scheduler. `public-enqueue-scheduled` inserts one scheduled
crawl job immediately, which is useful when you want the worker to process a run
without waiting for the next configured wall-clock time.

`public-api` starts the FastAPI service used by the Vercel frontend. Put it
behind Nginx or another TLS reverse proxy, and point
`NEXT_PUBLIC_GMGN_LABEL_API_URL` in `public-web` at that public HTTPS origin.

`public-reanalyze-recent --days 30 --clear-analysis` keeps raw `content_items`,
clears analysis/materialized outputs, and force-runs the current stock-only
signal extraction over the latest thirty Asia/Shanghai natural days.

`public-reanalyze-recent --domain crypto --days 30 --clear-analysis` does the
same for crypto analysis only. It does not clear or rewrite stock analysis
outputs. `public-rebuild-timelines --domain crypto` rebuilds crypto author and
asset timelines from existing crypto analyses. `normalize-crypto-assets` reloads
`data/config/crypto_aliases.json`, rewrites existing crypto analysis identities,
and rebuilds the crypto materialized views.

`public-worker-doctor` is read-only. Run it on the server with the same
environment file as the worker to print queue counts, due pending jobs, running
job age, latest scheduled job, global plus per-domain account/subscription
counts, onchain OKX-key presence, onchain wallet counts, latest onchain run,
and whether a job is holding the Postgres worker lock at that instant.

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

`public-generate-stock-narrative` generates the public stock narrative brief
from the materialized stock views. It reads the latest available stock viewpoint
date by default, or a specific `--date`, and skips an already successful brief
unless `--force` is passed. Logs include only status, window, counts, and token
usage; they must not print the prompt payload, DSN, or AI key.

`public-generate-crypto-asset-briefs` generates one frozen brief per visible
crypto asset and pins the model to `gpt-5.4-mini`. The worker runs this stage at
`PUBLIC_WORKER_CRYPTO_ASSET_BRIEF_TIME`, default `22:50` Asia/Shanghai.

The brief pipeline now also writes `identity_status`:

- `anchored`: CA or existing identifier match confirmed the project
- `fuzzy`: summary is usable but not hard-pinned by CA
- `ambiguous`: summary is intentionally conservative because same-name or
  generic-word noise is high

The crypto brief pipeline is:

1. Reuse existing `crypto_entities.contract_addresses_json` and stored raw identifiers first.
2. If unresolved, query OKX Onchain OS token search for up to five CA candidates.
3. Build a name-group X search set from display name, symbol, aliases, project accounts, and AI-expanded short keywords through the backend-owned browser search runtime.
4. Build a candidate-group X search set for each CA candidate from the CA itself, `"CA" + display_name`, and `"CA" + symbol`.
5. Cheap-filter obvious mismatches by shared accounts, aliases, keywords, and project fragments.
6. Let `gpt-5.4-mini` judge whether the surviving name-group and CA-group tweets are discussing the same project.
7. Accept only candidates with `same_project=true`, `confidence >= 0.75`, and at least one stable shared-signal rule.
8. Assess whether the asset is `anchored`, `fuzzy`, or `ambiguous`.
9. Generate a 1-2 sentence Chinese summary answering what the token/project does and the current X narrative or crowd perception.

Successful asset briefs are skipped on later runs unless `--force` is passed.
If CA resolution fails, the job still tries to summarize from the name-group
alone when enough X samples exist. The frontend only receives
`summary`, `summary_status`, `identity_status`, and `summary_updated_at` from
the crypto matrix RPC; it does not expose CA candidates or internal
similarity-judgment payloads.

Crypto admin controls add two more guards:

- blocked terms: if an asset matches a blocked term such as `base`, the brief
  worker writes `status=skipped` and does not run any later X/OKX/AI steps
- deleted assets: if an admin deletes an asset from the crypto overview, that
  `asset_key` is hidden from visible crypto list/detail/overview RPCs and is no
  longer selected by the brief worker

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

Create `/etc/systemd/system/jibai-public-api.service`:

```ini
[Unit]
Description=Jibai public API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/Jibai
EnvironmentFile=/etc/jibai/public-worker.env
ExecStart=/opt/Jibai/.venv/bin/python backend/src/main.py public-api --host 127.0.0.1 --port 8010
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then run:

```bash
systemctl daemon-reload
systemctl enable --now jibai-public-api
systemctl status jibai-public-api
journalctl -u jibai-public-api -f
```
