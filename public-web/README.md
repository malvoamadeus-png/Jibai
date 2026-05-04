# Jibai Public Web

Supabase-backed public X account tracker. This app is intentionally separate from `frontend/`.

## Required environment

Copy `.env.example` to `.env.local` and set:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

Run locally:

```bash
npm install
npm run dev
```

## Supabase setup

Apply these migrations to the Supabase project:

- `../supabase/migrations/001_public_schema.sql`
- `../supabase/migrations/002_direct_client_mode.sql`

Then bootstrap the admin email in Supabase SQL editor:

```sql
insert into public.admin_emails(email)
values ('you@example.com')
on conflict do nothing;
```

Enable the Google provider in Supabase Auth. Add this callback URL in the Google OAuth app and Supabase Auth settings:

```text
https://your-project-ref.supabase.co/auth/v1/callback
```

In Supabase Auth URL Configuration, set the public web callback URLs:

```text
http://localhost:3000/auth/callback
https://your-public-web-domain.com/auth/callback
```

Admin access is controlled by `public.admin_emails` in Supabase. This public-web app no longer uses Next API routes or a Supabase service role key.
