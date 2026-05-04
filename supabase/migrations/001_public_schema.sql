create extension if not exists pgcrypto;
create extension if not exists citext;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email citext not null unique,
  display_name text not null default '',
  avatar_url text not null default '',
  is_admin boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.x_accounts (
  id uuid primary key default gen_random_uuid(),
  username citext not null unique,
  display_name text not null default '',
  profile_url text not null,
  x_user_id text,
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'rejected', 'disabled')),
  submitted_by uuid references public.profiles(id) on delete set null,
  approved_by uuid references public.profiles(id) on delete set null,
  approved_at timestamptz,
  rejected_at timestamptz,
  disabled_at timestamptz,
  backfill_completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.account_requests (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.x_accounts(id) on delete cascade,
  requester_id uuid not null references public.profiles(id) on delete cascade,
  raw_input text not null,
  normalized_username citext not null,
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'rejected')),
  review_note text not null default '',
  reviewed_by uuid references public.profiles(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(account_id, requester_id)
);

create table if not exists public.user_subscriptions (
  user_id uuid not null references public.profiles(id) on delete cascade,
  account_id uuid not null references public.x_accounts(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key(user_id, account_id)
);

create table if not exists public.crawl_jobs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('scheduled_crawl', 'manual_crawl', 'initial_backfill')),
  status text not null default 'pending'
    check (status in ('pending', 'running', 'succeeded', 'failed')),
  account_id uuid references public.x_accounts(id) on delete cascade,
  requested_by uuid references public.profiles(id) on delete set null,
  dedupe_key text unique,
  run_after timestamptz not null default now(),
  locked_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  summary text not null default '',
  error_text text,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.content_items (
  id uuid primary key default gen_random_uuid(),
  platform text not null default 'x',
  account_id uuid not null references public.x_accounts(id) on delete cascade,
  external_content_id text not null,
  url text,
  title text,
  body_text text,
  content_type text,
  publish_time timestamptz,
  last_update_time timestamptz,
  fetched_at timestamptz,
  like_count integer,
  collect_count integer,
  comment_count integer,
  share_count integer,
  is_pinned boolean not null default false,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(platform, external_content_id)
);

create table if not exists public.content_analyses (
  id uuid primary key default gen_random_uuid(),
  content_id uuid not null unique references public.content_items(id) on delete cascade,
  date_key text not null,
  extracted_at timestamptz not null,
  summary_text text not null,
  key_points_json jsonb not null default '[]'::jsonb,
  raw_response_json jsonb not null default '{}'::jsonb,
  model_name text,
  request_id text,
  usage_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.security_entities (
  id uuid primary key default gen_random_uuid(),
  security_key text not null unique,
  display_name text not null,
  ticker text,
  market text,
  aliases_json jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.theme_entities (
  id uuid primary key default gen_random_uuid(),
  theme_key text not null unique,
  display_name text not null,
  aliases_json jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.security_mentions (
  id uuid primary key default gen_random_uuid(),
  content_id uuid not null references public.content_items(id) on delete cascade,
  security_id uuid not null references public.security_entities(id) on delete cascade,
  raw_name text not null,
  stock_name text,
  stance text not null,
  direction text not null default 'unknown',
  judgment_type text not null default 'unknown',
  conviction text not null default 'unknown',
  evidence_type text not null default 'unknown',
  view_summary text not null default '',
  evidence text not null default '',
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(content_id, security_id, raw_name, sort_order)
);

create table if not exists public.content_viewpoints (
  id uuid primary key default gen_random_uuid(),
  content_id uuid not null references public.content_items(id) on delete cascade,
  entity_type text not null,
  entity_key text not null,
  entity_name text not null,
  entity_code_or_name text,
  stance text not null,
  direction text not null default 'unknown',
  judgment_type text not null default 'unknown',
  conviction text not null default 'unknown',
  evidence_type text not null default 'unknown',
  logic text not null default '',
  evidence text not null default '',
  time_horizon text not null default 'unspecified',
  sort_order integer not null default 0,
  security_id uuid references public.security_entities(id) on delete set null,
  theme_id uuid references public.theme_entities(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(content_id, entity_type, entity_key, sort_order)
);

create table if not exists public.author_daily_summaries (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.x_accounts(id) on delete cascade,
  date_key text not null,
  status text not null,
  note_count_today integer not null default 0,
  summary_text text not null,
  note_ids_json jsonb not null default '[]'::jsonb,
  notes_json jsonb not null default '[]'::jsonb,
  viewpoints_json jsonb not null default '[]'::jsonb,
  mentioned_stocks_json jsonb not null default '[]'::jsonb,
  mentioned_themes_json jsonb not null default '[]'::jsonb,
  content_hash text not null default '',
  error_text text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(account_id, date_key)
);

create table if not exists public.security_daily_views (
  id uuid primary key default gen_random_uuid(),
  security_id uuid not null references public.security_entities(id) on delete cascade,
  date_key text not null,
  mention_count integer not null default 0,
  author_views_json jsonb not null default '[]'::jsonb,
  content_hash text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(security_id, date_key)
);

create table if not exists public.theme_daily_views (
  id uuid primary key default gen_random_uuid(),
  theme_id uuid not null references public.theme_entities(id) on delete cascade,
  date_key text not null,
  mention_count integer not null default 0,
  author_views_json jsonb not null default '[]'::jsonb,
  content_hash text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(theme_id, date_key)
);

create table if not exists public.crawl_runs (
  id uuid primary key default gen_random_uuid(),
  run_id text not null unique,
  run_at timestamptz not null,
  processed_note_count integer not null default 0,
  error_count integer not null default 0,
  errors_json jsonb not null default '[]'::jsonb,
  snapshot_path text,
  created_at timestamptz not null default now()
);

create table if not exists public.crawl_account_runs (
  id uuid primary key default gen_random_uuid(),
  crawl_run_id uuid references public.crawl_runs(id) on delete cascade,
  platform text not null default 'x',
  account_id uuid references public.x_accounts(id) on delete cascade,
  account_name text not null,
  run_at timestamptz not null,
  status text not null,
  candidate_count integer not null default 0,
  new_note_count integer not null default 0,
  fetched_note_ids_json jsonb not null default '[]'::jsonb,
  error_text text,
  created_at timestamptz not null default now()
);

create index if not exists idx_x_accounts_status on public.x_accounts(status, updated_at desc);
create index if not exists idx_account_requests_status on public.account_requests(status, created_at desc);
create index if not exists idx_user_subscriptions_user on public.user_subscriptions(user_id, account_id);
create index if not exists idx_crawl_jobs_status on public.crawl_jobs(status, run_after, created_at);
create index if not exists idx_content_items_account_publish on public.content_items(account_id, publish_time desc);
create index if not exists idx_author_daily_summaries_account_date on public.author_daily_summaries(account_id, date_key desc);
create index if not exists idx_content_viewpoints_entity on public.content_viewpoints(entity_type, entity_key, content_id);

drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists set_x_accounts_updated_at on public.x_accounts;
create trigger set_x_accounts_updated_at before update on public.x_accounts
for each row execute function public.set_updated_at();

drop trigger if exists set_account_requests_updated_at on public.account_requests;
create trigger set_account_requests_updated_at before update on public.account_requests
for each row execute function public.set_updated_at();

drop trigger if exists set_crawl_jobs_updated_at on public.crawl_jobs;
create trigger set_crawl_jobs_updated_at before update on public.crawl_jobs
for each row execute function public.set_updated_at();

alter table public.profiles enable row level security;
alter table public.x_accounts enable row level security;
alter table public.account_requests enable row level security;
alter table public.user_subscriptions enable row level security;
alter table public.content_items enable row level security;
alter table public.content_analyses enable row level security;
alter table public.content_viewpoints enable row level security;
alter table public.security_entities enable row level security;
alter table public.theme_entities enable row level security;
alter table public.author_daily_summaries enable row level security;
alter table public.security_daily_views enable row level security;
alter table public.theme_daily_views enable row level security;
alter table public.crawl_runs enable row level security;
alter table public.crawl_account_runs enable row level security;
alter table public.crawl_jobs enable row level security;

drop policy if exists "profiles owner read" on public.profiles;
create policy "profiles owner read" on public.profiles
for select to authenticated using (id = auth.uid());

drop policy if exists "profiles owner update" on public.profiles;
create policy "profiles owner update" on public.profiles
for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists "approved accounts readable" on public.x_accounts;
create policy "approved accounts readable" on public.x_accounts
for select to authenticated using (status = 'approved');

drop policy if exists "own requests readable" on public.account_requests;
create policy "own requests readable" on public.account_requests
for select to authenticated using (requester_id = auth.uid());

drop policy if exists "own subscriptions readable" on public.user_subscriptions;
create policy "own subscriptions readable" on public.user_subscriptions
for select to authenticated using (user_id = auth.uid());
