# Jibai Public Web

Supabase-backed public X account tracker. This app is intentionally separate from `frontend/`.

## Required environment

Copy `.env.example` to `.env.local` and set:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ADMIN_EMAILS`
- `NEXT_PUBLIC_SITE_URL`

Run locally:

```bash
npm install
npm run dev
```

## Supabase setup

Apply `../supabase/migrations/001_public_schema.sql` to the Supabase project, then enable the Google provider in Supabase Auth. Add this callback URL in the Google OAuth app and Supabase Auth settings:

```text
https://your-project-ref.supabase.co/auth/v1/callback
```

In Supabase Auth URL Configuration, set the public web callback URLs:

```text
http://localhost:3000/api/auth/callback
https://your-public-web-domain.com/api/auth/callback
```

Only emails listed in `ADMIN_EMAILS` can use admin APIs and the admin page.
