# Public Supabase Worker

The public edition uses Supabase as the primary database. Vercel runs `public-web/`; the Linux server only runs this Python worker.

## Environment

Set one Postgres connection string:

- `SUPABASE_DB_URL`
- or `DATABASE_URL`

Optional worker settings:

- `PUBLIC_WORKER_CRAWL_TIMES=04:00,10:00,16:00,22:00`
- `PUBLIC_WORKER_ACCOUNT_DELAY_SECONDS=5`
- `PUBLIC_WORKER_POLL_SECONDS=30`
- `PUBLIC_WORKER_HEADLESS=true`
- `PUBLIC_WORKER_PAGE_WAIT_SECONDS=6`

AI settings continue to use the existing backend configuration files and environment variables.

## Commands

```bash
python backend/src/main.py public-worker
python backend/src/main.py public-worker --once
python backend/src/main.py public-enqueue-scheduled
python backend/src/main.py public-import-sqlite
```

`public-worker` schedules four Asia/Shanghai crawl windows and polls Supabase for pending jobs. Jobs are processed serially with a database advisory lock, so multiple worker processes will not crawl at the same time.
