# Jibai Public Web

Public X account tracker for the Vercel-facing site. This app is intentionally
separate from `frontend/`.

## Required environment

Copy `.env.example` to `.env.local` and set:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_PUBLIC_API_BASE_URL`

If `NEXT_PUBLIC_PUBLIC_API_BASE_URL` is unset in a production build, the app
falls back to `https://api.47.76.243.147.sslip.io`.

Run locally:

```bash
..\install.cmd
..\dev.cmd public-web run dev
```

On Windows PowerShell, prefer `..\dev.cmd public-web ...` or `npm.cmd ...`
instead of bare `npm ...`, because some machines block `npm.ps1` via execution
policy. `..\install.cmd` also creates the repo-local Python virtualenv used by
backend tooling and tests.

## Auth and API setup

Supabase only handles Google login and session issuance for this app. Business
data now comes from the Linux public API over `NEXT_PUBLIC_PUBLIC_API_BASE_URL`.

Supabase still needs Google Auth configured:

- Enable the Google provider in Supabase Auth.
- Add `https://your-project-ref.supabase.co/auth/v1/callback` to the Google
  OAuth app and Supabase Auth provider settings.
- In Supabase Auth URL Configuration, allow:
  - `http://localhost:3000/auth/callback`
  - `https://your-public-web-domain.com/auth/callback`

The Linux public API must be deployed separately and must accept the Vercel
origin through `PUBLIC_API_ALLOWED_ORIGINS`.

## Linux public API

Run locally:

```bash
python backend/src/main.py public-api --host 127.0.0.1 --port 8010
```

Required Linux/API-side environment includes:

- `PUBLIC_APP_DB_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `PUBLIC_API_ALLOWED_ORIGINS`

The browser no longer reads business data directly from Supabase tables or RPCs.

## Linux database bootstrap

Initialize the Linux business database schema:

```bash
python backend/src/main.py public-bootstrap-linux-db
```

Copy business data from the existing Supabase Postgres database into the Linux
business database:

```bash
python backend/src/main.py public-copy-supabase-data
```

This command reads from `SUPABASE_DB_URL` / `DATABASE_URL` and writes to
`PUBLIC_APP_DB_URL`.

## Admin bootstrap

Seed admin email in the Linux business database:

```sql
insert into public.admin_emails(email)
values ('you@example.com')
on conflict do nothing;
```
