-- Add stock/crypto domain isolation and crypto public read surfaces.
-- Existing stock data is preserved as domain='stock'.

alter table public.account_requests
  add column if not exists domain text not null default 'stock';

alter table public.user_subscriptions
  add column if not exists domain text not null default 'stock';

alter table public.crawl_jobs
  add column if not exists domain text not null default 'stock';

alter table public.crawl_runs
  add column if not exists analysis_domain text not null default 'stock';

alter table public.content_analyses
  add column if not exists analysis_domain text not null default 'stock';

alter table public.content_viewpoints
  add column if not exists analysis_domain text not null default 'stock',
  add column if not exists metadata_json jsonb not null default '{}'::jsonb;

alter table public.author_daily_summaries
  add column if not exists analysis_domain text not null default 'stock',
  add column if not exists mentioned_crypto_json jsonb not null default '[]'::jsonb;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'account_requests_domain_check') then
    alter table public.account_requests
      add constraint account_requests_domain_check check (domain in ('stock', 'crypto'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'user_subscriptions_domain_check') then
    alter table public.user_subscriptions
      add constraint user_subscriptions_domain_check check (domain in ('stock', 'crypto'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'crawl_jobs_domain_check') then
    alter table public.crawl_jobs
      add constraint crawl_jobs_domain_check check (domain in ('stock', 'crypto'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'crawl_runs_analysis_domain_check') then
    alter table public.crawl_runs
      add constraint crawl_runs_analysis_domain_check check (analysis_domain in ('stock', 'crypto'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'content_analyses_analysis_domain_check') then
    alter table public.content_analyses
      add constraint content_analyses_analysis_domain_check check (analysis_domain in ('stock', 'crypto'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'content_viewpoints_analysis_domain_check') then
    alter table public.content_viewpoints
      add constraint content_viewpoints_analysis_domain_check check (analysis_domain in ('stock', 'crypto'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'author_daily_summaries_analysis_domain_check') then
    alter table public.author_daily_summaries
      add constraint author_daily_summaries_analysis_domain_check check (analysis_domain in ('stock', 'crypto'));
  end if;
end $$;

create table if not exists public.account_domains (
  account_id uuid not null references public.x_accounts(id) on delete cascade,
  domain text not null check (domain in ('stock', 'crypto')),
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'rejected', 'disabled')),
  approved_by uuid references public.profiles(id) on delete set null,
  approved_at timestamptz,
  rejected_at timestamptz,
  disabled_at timestamptz,
  backfill_completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key(account_id, domain)
);

insert into public.account_domains (
  account_id, domain, status, approved_by, approved_at, rejected_at,
  disabled_at, backfill_completed_at, created_at, updated_at
)
select
  id, 'stock', status, approved_by, approved_at, rejected_at,
  disabled_at, backfill_completed_at, created_at, updated_at
from public.x_accounts
on conflict (account_id, domain) do nothing;

insert into public.account_domains (account_id, domain, status)
select distinct account_id, domain, status
from public.account_requests
on conflict (account_id, domain) do nothing;

create table if not exists public.crypto_entities (
  id uuid primary key default gen_random_uuid(),
  asset_key text not null unique,
  display_name text not null,
  symbol text,
  identifier_type text not null default 'unknown',
  raw_identifiers_json jsonb not null default '[]'::jsonb,
  contract_addresses_json jsonb not null default '[]'::jsonb,
  x_accounts_json jsonb not null default '[]'::jsonb,
  aliases_json jsonb not null default '[]'::jsonb,
  category text,
  chain text,
  coingecko_id text,
  normalized_status text not null default 'temporary'
    check (normalized_status in ('canonical', 'temporary', 'needs_review')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.content_viewpoints
  add column if not exists crypto_entity_id uuid references public.crypto_entities(id) on delete set null;

create table if not exists public.crypto_entity_daily_views (
  id uuid primary key default gen_random_uuid(),
  crypto_entity_id uuid not null references public.crypto_entities(id) on delete cascade,
  date_key text not null,
  mention_count integer not null default 0,
  author_views_json jsonb not null default '[]'::jsonb,
  content_hash text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(crypto_entity_id, date_key)
);

alter table public.account_domains enable row level security;
alter table public.crypto_entities enable row level security;
alter table public.crypto_entity_daily_views enable row level security;

drop policy if exists "account domains direct read" on public.account_domains;
create policy "account domains direct read" on public.account_domains
for select to authenticated using (public.is_current_user_admin());

drop policy if exists "crypto entities readable" on public.crypto_entities;
create policy "crypto entities readable" on public.crypto_entities
for select to authenticated using (true);

drop policy if exists "crypto daily views readable" on public.crypto_entity_daily_views;
create policy "crypto daily views readable" on public.crypto_entity_daily_views
for select to authenticated using (true);

drop trigger if exists set_account_domains_updated_at on public.account_domains;
create trigger set_account_domains_updated_at before update on public.account_domains
for each row execute function public.set_updated_at();

drop trigger if exists set_crypto_entities_updated_at on public.crypto_entities;
create trigger set_crypto_entities_updated_at before update on public.crypto_entities
for each row execute function public.set_updated_at();

drop trigger if exists set_crypto_entity_daily_views_updated_at on public.crypto_entity_daily_views;
create trigger set_crypto_entity_daily_views_updated_at before update on public.crypto_entity_daily_views
for each row execute function public.set_updated_at();

drop index if exists idx_user_subscriptions_user;
alter table public.user_subscriptions drop constraint if exists user_subscriptions_pkey;
alter table public.user_subscriptions
  add primary key(user_id, account_id, domain);
create index if not exists idx_user_subscriptions_user_domain
  on public.user_subscriptions(user_id, domain, account_id);

alter table public.account_requests
  drop constraint if exists account_requests_account_id_requester_id_key;
create unique index if not exists account_requests_account_domain_requester_key
  on public.account_requests(account_id, domain, requester_id);

alter table public.content_analyses
  drop constraint if exists content_analyses_content_id_key;
create unique index if not exists content_analyses_content_domain_key
  on public.content_analyses(content_id, analysis_domain);

alter table public.author_daily_summaries
  drop constraint if exists author_daily_summaries_account_id_date_key_key;
create unique index if not exists author_daily_summaries_account_date_domain_key
  on public.author_daily_summaries(account_id, date_key, analysis_domain);

alter table public.content_viewpoints
  drop constraint if exists content_viewpoints_content_id_entity_type_entity_key_sort_order_key;
create unique index if not exists content_viewpoints_content_domain_entity_key
  on public.content_viewpoints(content_id, analysis_domain, entity_type, entity_key, sort_order);

create index if not exists idx_account_domains_domain_status
  on public.account_domains(domain, status, updated_at desc);
create index if not exists idx_crawl_jobs_domain_status
  on public.crawl_jobs(domain, status, run_after, created_at);
create index if not exists idx_content_analyses_domain
  on public.content_analyses(analysis_domain, date_key desc);
create index if not exists idx_content_viewpoints_domain_entity
  on public.content_viewpoints(analysis_domain, entity_type, entity_key, content_id);
create index if not exists idx_crypto_daily_entity_date
  on public.crypto_entity_daily_views(crypto_entity_id, date_key desc);

drop policy if exists "subscriptions direct insert" on public.user_subscriptions;
create policy "subscriptions direct insert" on public.user_subscriptions
for insert to authenticated
with check (
  user_id = auth.uid()
  and exists (
    select 1
    from public.account_domains ad
    where ad.account_id = user_subscriptions.account_id
      and ad.domain = user_subscriptions.domain
      and ad.status = 'approved'
  )
);

drop policy if exists "subscriptions direct delete" on public.user_subscriptions;
create policy "subscriptions direct delete" on public.user_subscriptions
for delete to authenticated using (user_id = auth.uid());

drop policy if exists "author summaries subscribed read" on public.author_daily_summaries;
create policy "author summaries subscribed read" on public.author_daily_summaries
for select to authenticated using (
  public.is_current_user_admin()
  or exists (
    select 1
    from public.user_subscriptions
    where user_subscriptions.user_id = auth.uid()
      and user_subscriptions.account_id = author_daily_summaries.account_id
      and user_subscriptions.domain = author_daily_summaries.analysis_domain
  )
);

drop policy if exists "content analyses subscribed read" on public.content_analyses;
create policy "content analyses subscribed read" on public.content_analyses
for select to authenticated using (
  public.is_current_user_admin()
  or exists (
    select 1
    from public.content_items
    join public.user_subscriptions on user_subscriptions.account_id = content_items.account_id
    where content_items.id = content_analyses.content_id
      and user_subscriptions.user_id = auth.uid()
      and user_subscriptions.domain = content_analyses.analysis_domain
  )
);

drop policy if exists "content viewpoints subscribed read" on public.content_viewpoints;
create policy "content viewpoints subscribed read" on public.content_viewpoints
for select to authenticated using (
  public.is_current_user_admin()
  or exists (
    select 1
    from public.content_items
    join public.user_subscriptions on user_subscriptions.account_id = content_items.account_id
    where content_items.id = content_viewpoints.content_id
      and user_subscriptions.user_id = auth.uid()
      and user_subscriptions.domain = content_viewpoints.analysis_domain
  )
);

create or replace function public.list_public_accounts(
  query_arg text,
  limit_arg integer,
  domain_arg text
)
returns table (
  id uuid,
  username text,
  display_name text,
  profile_url text,
  subscribed boolean,
  backfill_completed_at timestamptz
)
language sql
security definer
stable
set search_path = public
as $$
  select
    a.id,
    a.username::text,
    coalesce(nullif(a.display_name, ''), a.username::text)::text as display_name,
    a.profile_url::text,
    (
      auth.uid() is not null
      and exists (
        select 1
        from public.user_subscriptions s
        where s.user_id = auth.uid()
          and s.account_id = a.id
          and s.domain = coalesce(nullif(domain_arg, ''), 'stock')
      )
    ) as subscribed,
    ad.backfill_completed_at
  from public.x_accounts a
  join public.account_domains ad on ad.account_id = a.id
  where ad.domain = coalesce(nullif(domain_arg, ''), 'stock')
    and ad.status = 'approved'
    and (
      coalesce(trim(query_arg), '') = ''
      or lower(a.username::text) like '%' || lower(trim(query_arg)) || '%'
      or lower(coalesce(a.display_name, '')) like '%' || lower(trim(query_arg)) || '%'
    )
  order by coalesce(ad.approved_at, ad.updated_at, ad.created_at) desc, a.username::text asc
  limit least(greatest(coalesce(limit_arg, 100), 1), 500);
$$;

create or replace function public.list_public_accounts(
  query_arg text default '',
  limit_arg integer default 100
)
returns table (
  id uuid,
  username text,
  display_name text,
  profile_url text,
  subscribed boolean,
  backfill_completed_at timestamptz
)
language sql
security definer
stable
set search_path = public
as $$
  select * from public.list_public_accounts(query_arg, limit_arg, 'stock');
$$;

create or replace function public.submit_x_account(
  raw_input_arg text,
  username_arg text,
  domain_arg text
)
returns table (
  account_id uuid,
  request_id uuid,
  account_status text,
  request_status text
)
language plpgsql
security definer
set search_path = public
as $$
declare
  account_id_value uuid;
  request_id_value uuid;
  account_status_value text;
  request_status_value text;
  normalized_username citext;
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
begin
  if auth.uid() is null then
    raise exception 'Authentication required.';
  end if;

  normalized_username := lower(trim(username_arg))::citext;
  if normalized_username::text !~ '^[a-z0-9_]{1,15}$' then
    raise exception 'Invalid X username.';
  end if;

  select id into account_id_value
  from public.x_accounts
  where username = normalized_username;

  if account_id_value is null then
    insert into public.x_accounts (username, display_name, profile_url, status, submitted_by)
    values (
      normalized_username,
      normalized_username::text,
      'https://x.com/' || normalized_username::text,
      'pending',
      auth.uid()
    )
    returning id into account_id_value;
  end if;

  insert into public.account_domains (account_id, domain, status)
  values (account_id_value, safe_domain, 'pending')
  on conflict (account_id, domain) do nothing;

  select status
  into account_status_value
  from public.account_domains
  where account_id = account_id_value
    and domain = safe_domain;

  request_status_value := case when account_status_value = 'approved' then 'approved' else 'pending' end;

  insert into public.account_requests (
    account_id,
    requester_id,
    raw_input,
    normalized_username,
    domain,
    status,
    reviewed_at
  )
  values (
    account_id_value,
    auth.uid(),
    raw_input_arg,
    normalized_username,
    safe_domain,
    request_status_value,
    case when request_status_value = 'approved' then now() else null end
  )
  on conflict (account_id, domain, requester_id) do update
  set
    raw_input = excluded.raw_input,
    normalized_username = excluded.normalized_username,
    status = excluded.status,
    reviewed_at = excluded.reviewed_at,
    updated_at = now()
  returning id into request_id_value;

  if account_status_value = 'approved' then
    insert into public.user_subscriptions (user_id, account_id, domain)
    values (auth.uid(), account_id_value, safe_domain)
    on conflict do nothing;
  end if;

  return query select account_id_value, request_id_value, account_status_value, request_status_value;
end;
$$;

create or replace function public.submit_x_account(raw_input_arg text, username_arg text)
returns table (
  account_id uuid,
  request_id uuid,
  account_status text,
  request_status text
)
language sql
security definer
set search_path = public
as $$
  select * from public.submit_x_account(raw_input_arg, username_arg, 'stock');
$$;

grant execute on function public.submit_x_account(text, text) to authenticated;
grant execute on function public.submit_x_account(text, text, text) to authenticated;

create or replace function public.approve_account_request(request_id_arg uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  account_id_value uuid;
  request_domain text;
  existing_status text;
  approved_count integer;
  backfill_completed_at_value timestamptz;
  should_enqueue_backfill boolean;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin access required.';
  end if;

  select account_id, domain
  into account_id_value, request_domain
  from public.account_requests
  where id = request_id_arg;

  if account_id_value is null then
    raise exception 'Request not found.';
  end if;

  select status, backfill_completed_at
  into existing_status, backfill_completed_at_value
  from public.account_domains
  where account_id = account_id_value
    and domain = request_domain;

  if existing_status is distinct from 'approved' then
    select count(*) into approved_count
    from public.account_domains
    where domain = request_domain
      and status = 'approved';

    if approved_count >= 100 then
      raise exception 'Approved X account limit reached.';
    end if;
  end if;

  should_enqueue_backfill :=
    existing_status is distinct from 'approved'
    and backfill_completed_at_value is null;

  update public.x_accounts
  set
    status = 'approved',
    approved_by = auth.uid(),
    approved_at = coalesce(approved_at, now()),
    rejected_at = null,
    disabled_at = null
  where id = account_id_value;

  insert into public.account_domains (
    account_id, domain, status, approved_by, approved_at, rejected_at, disabled_at
  )
  values (
    account_id_value, request_domain, 'approved', auth.uid(), now(), null, null
  )
  on conflict (account_id, domain) do update
  set
    status = 'approved',
    approved_by = auth.uid(),
    approved_at = now(),
    rejected_at = null,
    disabled_at = null,
    updated_at = now();

  update public.account_requests
  set
    status = 'approved',
    reviewed_by = auth.uid(),
    reviewed_at = now()
  where account_id = account_id_value
    and domain = request_domain
    and status = 'pending';

  insert into public.user_subscriptions (user_id, account_id, domain)
  select requester_id, account_id_value, request_domain
  from public.account_requests
  where account_id = account_id_value
    and domain = request_domain
    and status = 'approved'
  on conflict do nothing;

  if should_enqueue_backfill then
    insert into public.crawl_jobs (
      kind,
      status,
      account_id,
      domain,
      requested_by,
      dedupe_key,
      metadata_json
    )
    values (
      'initial_backfill',
      'pending',
      account_id_value,
      request_domain,
      auth.uid(),
      'initial_backfill:' || request_domain || ':' || account_id_value::text,
      jsonb_build_object(
        'source', 'approve',
        'domain', request_domain,
        'window_days', 30,
        'target_count', 30,
        'skip_old_pinned', true
      )
    )
    on conflict (dedupe_key) do nothing;
  end if;
end;
$$;

grant execute on function public.approve_account_request(uuid) to authenticated;

create or replace function public.reject_account_request(request_id_arg uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  account_id_value uuid;
  request_domain text;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin access required.';
  end if;

  select account_id, domain
  into account_id_value, request_domain
  from public.account_requests
  where id = request_id_arg;

  if account_id_value is null then
    raise exception 'Request not found.';
  end if;

  update public.account_requests
  set
    status = 'rejected',
    reviewed_by = auth.uid(),
    reviewed_at = now()
  where id = request_id_arg;

  update public.account_domains
  set
    status = 'rejected',
    rejected_at = now(),
    updated_at = now()
  where account_id = account_id_value
    and domain = request_domain
    and not exists (
      select 1
      from public.account_requests ar
      where ar.account_id = account_id_value
        and ar.domain = request_domain
        and ar.status = 'approved'
    );
end;
$$;

grant execute on function public.reject_account_request(uuid) to authenticated;

create or replace function public.disable_x_account(account_id_arg uuid, domain_arg text)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin access required.';
  end if;

  update public.account_domains
  set
    status = 'disabled',
    disabled_at = now(),
    updated_at = now()
  where account_id = account_id_arg
    and domain = safe_domain;

  delete from public.user_subscriptions
  where account_id = account_id_arg
    and domain = safe_domain;

  update public.x_accounts
  set
    status = case
      when exists (
        select 1 from public.account_domains
        where account_id = account_id_arg
          and status = 'approved'
      ) then 'approved'
      else 'disabled'
    end,
    disabled_at = now(),
    updated_at = now()
  where id = account_id_arg;
end;
$$;

create or replace function public.disable_x_account(account_id_arg uuid)
returns void
language sql
security definer
set search_path = public
as $$
  select public.disable_x_account(account_id_arg, 'stock');
$$;

grant execute on function public.disable_x_account(uuid) to authenticated;
grant execute on function public.disable_x_account(uuid, text) to authenticated;

create or replace function public.enqueue_manual_crawl(domain_arg text)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  job_id_value uuid;
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin access required.';
  end if;

  insert into public.crawl_jobs (
    kind,
    status,
    domain,
    requested_by,
    metadata_json
  )
  values (
    'manual_crawl',
    'pending',
    safe_domain,
    auth.uid(),
    jsonb_build_object('source', 'admin-ui', 'domain', safe_domain)
  )
  returning id into job_id_value;

  return job_id_value;
end;
$$;

grant execute on function public.enqueue_manual_crawl(text) to authenticated;

create or replace function public.enqueue_manual_crawl()
returns uuid
language sql
security definer
set search_path = public
as $$
  select public.enqueue_manual_crawl('stock');
$$;

grant execute on function public.enqueue_manual_crawl() to authenticated;

create or replace function public.list_visible_authors(
  query_arg text,
  limit_arg integer,
  domain_arg text
)
returns table (
  account_id uuid,
  platform text,
  account_name text,
  author_nickname text,
  profile_url text,
  latest_date text,
  latest_status text,
  total_days integer,
  total_notes integer,
  updated_at timestamptz
)
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  safe_limit integer;
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
begin
  safe_limit := case
    when current_uid is null then 1
    else least(greatest(coalesce(limit_arg, 100), 1), 500)
  end;

  return query
  with visible_accounts as (
    select a.*
    from public.x_accounts a
    join public.account_domains ad on ad.account_id = a.id
    where ad.domain = safe_domain
      and ad.status = 'approved'
      and (
        current_uid is null
        or current_is_admin
        or exists (
          select 1
          from public.user_subscriptions s
          where s.user_id = current_uid
            and s.account_id = a.id
            and s.domain = safe_domain
        )
      )
  ),
  eligible_days as (
    select
      va.id,
      va.username,
      va.display_name,
      va.profile_url,
      ads.date_key,
      ads.status,
      ads.note_count_today,
      ads.updated_at
    from visible_accounts va
    join public.author_daily_summaries ads on ads.account_id = va.id
    where ads.analysis_domain = safe_domain
      and exists (
        select 1
        from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) as viewpoint(value)
        where (
          safe_domain = 'crypto'
          and coalesce(viewpoint.value ->> 'entity_type', '') = 'crypto_entity'
        )
        or (
          safe_domain = 'stock'
          and coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
          and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
          and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
          and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
        )
      )
  )
  select
    d.id as account_id,
    'x'::text as platform,
    d.username::text as account_name,
    coalesce(nullif(d.display_name, ''), d.username::text)::text as author_nickname,
    d.profile_url::text,
    max(d.date_key)::text as latest_date,
    (array_agg(d.status order by d.date_key desc))[1]::text as latest_status,
    count(*)::integer as total_days,
    coalesce(sum(d.note_count_today), 0)::integer as total_notes,
    max(d.updated_at) as updated_at
  from eligible_days d
  where (
    current_uid is null
    or coalesce(trim(query_arg), '') = ''
    or lower(d.username::text) like '%' || lower(trim(query_arg)) || '%'
    or lower(coalesce(d.display_name, '')) like '%' || lower(trim(query_arg)) || '%'
  )
  group by d.id, d.username, d.display_name, d.profile_url
  order by max(d.date_key) desc, max(d.updated_at) desc, d.username::text asc
  limit safe_limit;
end;
$$;

create or replace function public.list_visible_authors(
  query_arg text default '',
  limit_arg integer default 100
)
returns table (
  account_id uuid,
  platform text,
  account_name text,
  author_nickname text,
  profile_url text,
  latest_date text,
  latest_status text,
  total_days integer,
  total_notes integer,
  updated_at timestamptz
)
language sql
security definer
stable
set search_path = public
as $$
  select * from public.list_visible_authors(query_arg, limit_arg, 'stock');
$$;

create or replace function public.get_visible_author_timeline(
  account_id_arg uuid,
  page_arg integer,
  page_size_arg integer,
  domain_arg text
)
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  safe_page integer := greatest(coalesce(page_arg, 1), 1);
  safe_page_size integer;
  offset_value integer;
  preview_account_id uuid;
  can_view boolean := false;
  total_count integer := 0;
  meta_payload jsonb;
  rows_payload jsonb;
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
begin
  safe_page_size := case
    when current_uid is null then least(greatest(coalesce(page_size_arg, 3), 1), 3)
    else least(greatest(coalesce(page_size_arg, 20), 1), 100)
  end;
  offset_value := (safe_page - 1) * safe_page_size;

  select ranked.account_id
  into preview_account_id
  from (
    select
      a.id as account_id,
      max(ads.date_key) as latest_date,
      max(ads.updated_at) as latest_updated_at
    from public.x_accounts a
    join public.account_domains ad on ad.account_id = a.id and ad.domain = safe_domain
    join public.author_daily_summaries ads on ads.account_id = a.id
    where ad.status = 'approved'
      and ads.analysis_domain = safe_domain
      and exists (
        select 1
        from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) as viewpoint(value)
        where (
          safe_domain = 'crypto'
          and coalesce(viewpoint.value ->> 'entity_type', '') = 'crypto_entity'
        )
        or (
          safe_domain = 'stock'
          and coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
          and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
          and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
          and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
        )
      )
    group by a.id
    order by max(ads.date_key) desc, max(ads.updated_at) desc
    limit 1
  ) ranked;

  select exists (
    select 1
    from public.x_accounts a
    join public.account_domains ad on ad.account_id = a.id
    where a.id = account_id_arg
      and ad.domain = safe_domain
      and ad.status = 'approved'
      and (
        current_is_admin
        or (current_uid is not null and exists (
          select 1
          from public.user_subscriptions s
          where s.user_id = current_uid
            and s.account_id = a.id
            and s.domain = safe_domain
        ))
        or (current_uid is null and a.id = preview_account_id)
      )
  )
  into can_view;

  if not can_view then
    return null;
  end if;

  select count(*)::integer
  into total_count
  from public.author_daily_summaries ads
  where ads.account_id = account_id_arg
    and ads.analysis_domain = safe_domain
    and exists (
      select 1
      from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) as viewpoint(value)
      where (
        safe_domain = 'crypto'
        and coalesce(viewpoint.value ->> 'entity_type', '') = 'crypto_entity'
      )
      or (
        safe_domain = 'stock'
        and coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
        and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
        and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
        and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
      )
    );

  if total_count = 0 then
    return null;
  end if;

  select jsonb_build_object(
    'account_id', a.id,
    'platform', 'x',
    'account_name', a.username::text,
    'author_nickname', coalesce(nullif(a.display_name, ''), a.username::text),
    'author_id', coalesce(a.x_user_id, ''),
    'profile_url', a.profile_url
  )
  into meta_payload
  from public.x_accounts a
  where a.id = account_id_arg
  limit 1;

  select coalesce(jsonb_agg(day_payload order by date_key desc), '[]'::jsonb)
  into rows_payload
  from (
    select
      ads.date_key,
      jsonb_build_object(
        'date', ads.date_key,
        'status', ads.status,
        'note_count_today', ads.note_count_today,
        'summary_text', case when safe_domain = 'crypto' then '' else ads.summary_text end,
        'note_ids', coalesce(ads.note_ids_json, '[]'::jsonb),
        'notes', coalesce(ads.notes_json, '[]'::jsonb),
        'viewpoints', (
          select coalesce(jsonb_agg(viewpoint.value order by viewpoint.ordinality), '[]'::jsonb)
          from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) with ordinality as viewpoint(value, ordinality)
          where (
            safe_domain = 'crypto'
            and coalesce(viewpoint.value ->> 'entity_type', '') = 'crypto_entity'
          )
          or (
            safe_domain = 'stock'
            and coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
            and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
            and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
            and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
          )
        ),
        'mentioned_stocks', coalesce(ads.mentioned_stocks_json, '[]'::jsonb),
        'mentioned_themes', coalesce(ads.mentioned_themes_json, '[]'::jsonb),
        'mentioned_crypto', coalesce(ads.mentioned_crypto_json, '[]'::jsonb),
        'updated_at', ads.updated_at
      ) as day_payload
    from public.author_daily_summaries ads
    where ads.account_id = account_id_arg
      and ads.analysis_domain = safe_domain
      and exists (
        select 1
        from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) as viewpoint(value)
        where (
          safe_domain = 'crypto'
          and coalesce(viewpoint.value ->> 'entity_type', '') = 'crypto_entity'
        )
        or (
          safe_domain = 'stock'
          and coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
          and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
          and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
          and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
        )
      )
    order by ads.date_key desc
    limit safe_page_size offset offset_value
  ) page_rows;

  return jsonb_build_object(
    'meta', meta_payload,
    'timeline', jsonb_build_object(
      'rows', rows_payload,
      'total', total_count,
      'page', safe_page,
      'page_size', safe_page_size,
      'total_pages', greatest(1, ceil(total_count::numeric / safe_page_size)::integer)
    )
  );
end;
$$;

create or replace function public.get_visible_author_timeline(
  account_id_arg uuid,
  page_arg integer default 1,
  page_size_arg integer default 20
)
returns jsonb
language sql
security definer
stable
set search_path = public
as $$
  select public.get_visible_author_timeline(account_id_arg, page_arg, page_size_arg, 'stock');
$$;

create or replace function public.list_visible_entities(
  entity_type_arg text,
  query_arg text default '',
  limit_arg integer default 100
)
returns table (
  entity_key text,
  display_name text,
  ticker text,
  market text,
  latest_date text,
  mention_days integer,
  total_mentions integer,
  updated_at timestamptz
)
language plpgsql
security definer
stable
set search_path = public
as $$
begin
  return query
  select *
  from public.list_visible_entities(entity_type_arg, query_arg, limit_arg, 'date_desc');
end;
$$;

create or replace function public.list_visible_entities(
  entity_type_arg text,
  query_arg text,
  limit_arg integer,
  sort_arg text
)
returns table (
  entity_key text,
  display_name text,
  ticker text,
  market text,
  latest_date text,
  mention_days integer,
  total_mentions integer,
  updated_at timestamptz
)
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  safe_limit integer;
  safe_sort text;
begin
  safe_limit := case
    when current_uid is null then 1
    else least(greatest(coalesce(limit_arg, 100), 1), 500)
  end;
  safe_sort := case
    when coalesce(sort_arg, '') in ('date_desc', 'date_asc', 'count_desc', 'count_asc') then sort_arg
    else 'date_desc'
  end;

  if entity_type_arg <> 'stock' then
    return;
  end if;

  return query
  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    join public.account_domains ad on ad.account_id = xa.id and ad.domain = 'stock'
    where s.user_id = current_uid
      and s.domain = 'stock'
      and ad.status = 'approved'
  ),
  expanded as (
    select
      se.security_key::text as key_value,
      se.display_name::text as display_value,
      se.ticker::text as ticker_value,
      se.market::text as market_value,
      sdv.date_key::text as date_value,
      sdv.updated_at,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
      and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
      and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
  )
  select
    e.key_value,
    e.display_value,
    e.ticker_value,
    e.market_value,
    max(e.date_value)::text,
    count(distinct e.date_value)::integer,
    count(*)::integer,
    max(e.updated_at)
  from expanded e
  where e.author_name <> ''
    and (
      current_uid is null
      or current_is_admin
      or e.author_name in (select va.author_name from visible_authors va)
    )
    and (
      current_uid is null
      or coalesce(trim(query_arg), '') = ''
      or lower(e.key_value) like '%' || lower(trim(query_arg)) || '%'
      or lower(e.display_value) like '%' || lower(trim(query_arg)) || '%'
      or lower(coalesce(e.ticker_value, '')) like '%' || lower(trim(query_arg)) || '%'
    )
  group by e.key_value, e.display_value, e.ticker_value, e.market_value
  order by
    case when safe_sort = 'date_desc' then max(e.date_value) end desc nulls last,
    case when safe_sort = 'date_asc' then max(e.date_value) end asc nulls last,
    case when safe_sort = 'count_desc' then count(*) end desc nulls last,
    case when safe_sort = 'count_asc' then count(*) end asc nulls last,
    e.display_value asc
  limit safe_limit;
end;
$$;

create or replace function public.get_visible_entity_timeline(
  entity_type_arg text,
  entity_key_arg text,
  page_arg integer default 1,
  page_size_arg integer default 20
)
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  safe_page integer := greatest(coalesce(page_arg, 1), 1);
  safe_page_size integer;
  offset_value integer;
  preview_key text;
  total_count integer := 0;
  security_id_value uuid;
  meta_payload jsonb;
  rows_payload jsonb;
  markers_payload jsonb := '[]'::jsonb;
  candles_payload jsonb := '[]'::jsonb;
  chart_payload jsonb;
  latest_source text;
begin
  if entity_type_arg <> 'stock' then
    return null;
  end if;

  safe_page_size := case
    when current_uid is null then least(greatest(coalesce(page_size_arg, 3), 1), 3)
    else least(greatest(coalesce(page_size_arg, 20), 1), 100)
  end;
  offset_value := (safe_page - 1) * safe_page_size;

  select preview.key_value
  into preview_key
  from (
    select
      se.security_key::text as key_value,
      max(sdv.date_key) as latest_date,
      count(*) as total_mentions
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
      and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
      and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
      and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
    group by se.security_key
    order by max(sdv.date_key) desc, count(*) desc
    limit 1
  ) preview;

  if current_uid is null and coalesce(entity_key_arg, '') <> coalesce(preview_key, '') then
    return null;
  end if;

  select
    se.id,
    jsonb_build_object(
      'key', se.security_key,
      'display_name', se.display_name,
      'ticker', se.ticker,
      'market', se.market
    )
  into security_id_value, meta_payload
  from public.security_entities se
  where se.security_key = entity_key_arg
  limit 1;

  if meta_payload is null then
    return null;
  end if;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    join public.account_domains ad on ad.account_id = xa.id and ad.domain = 'stock'
    where s.user_id = current_uid
      and s.domain = 'stock'
      and ad.status = 'approved'
  ),
  raw_days as (
    select
      sdv.date_key,
      sdv.updated_at,
      (
        select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
        from jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
        where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
          and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
          and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
          and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
          and (
            current_uid is null
            or current_is_admin
            or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
              select va.author_name from visible_authors va
            )
          )
      ) as author_views
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    where se.security_key = entity_key_arg
  ),
  visible_days as (
    select *
    from raw_days
    where jsonb_array_length(author_views) > 0
  )
  select
    count(*)::integer,
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'date', date_key,
          'mention_count', jsonb_array_length(author_views),
          'author_views', author_views
        )
        order by date_key asc
      ),
      '[]'::jsonb
    )
  into total_count, markers_payload
  from visible_days;

  if total_count = 0 then
    return null;
  end if;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    join public.account_domains ad on ad.account_id = xa.id and ad.domain = 'stock'
    where s.user_id = current_uid
      and s.domain = 'stock'
      and ad.status = 'approved'
  ),
  raw_days as (
    select
      sdv.date_key,
      sdv.updated_at,
      (
        select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
        from jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
        where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
          and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
          and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
          and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
          and (
            current_uid is null
            or current_is_admin
            or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
              select va.author_name from visible_authors va
            )
          )
      ) as author_views
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    where se.security_key = entity_key_arg
  ),
  visible_days as (
    select *
    from raw_days
    where jsonb_array_length(author_views) > 0
    order by date_key desc
    limit safe_page_size offset offset_value
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'date', date_key,
        'mention_count', jsonb_array_length(author_views),
        'author_views', author_views,
        'updated_at', updated_at
      )
      order by date_key desc
    ),
    '[]'::jsonb
  )
  into rows_payload
  from visible_days;

  if current_uid is null then
    chart_payload := jsonb_build_object(
      'sourceLabel', null,
      'message', 'Sign in to view market data.',
      'candles', '[]'::jsonb,
      'markers', '[]'::jsonb
    );
  else
    select coalesce(
      jsonb_agg(
        jsonb_build_object(
          'date', date_key,
          'open', open_price,
          'high', high_price,
          'low', low_price,
          'close', close_price,
          'volume', volume
        )
        order by date_key asc
      ),
      '[]'::jsonb
    )
    into candles_payload
    from public.security_daily_prices
    where security_id = security_id_value
      and date_key >= (current_date - interval '180 days')::date::text;

    select source
    into latest_source
    from public.security_daily_prices
    where security_id = security_id_value
    order by date_key desc
    limit 1;

    chart_payload := jsonb_build_object(
      'sourceLabel', latest_source,
      'message', case
        when jsonb_array_length(candles_payload) > 0 then null
        else 'Market data is temporarily unavailable; the viewpoint timeline is still shown.'
      end,
      'candles', candles_payload,
      'markers', markers_payload
    );
  end if;

  return jsonb_build_object(
    'meta', meta_payload,
    'timeline', jsonb_build_object(
      'rows', rows_payload,
      'total', total_count,
      'page', safe_page,
      'page_size', safe_page_size,
      'total_pages', greatest(1, ceil(total_count::numeric / safe_page_size)::integer)
    ),
    'chart', chart_payload
  );
end;
$$;

create or replace function public.get_visible_stock_matrix(
  end_date_arg text default null
)
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  requested_end date;
  latest_visible_date date;
  effective_end date;
  effective_start date;
  previous_end date;
  next_end date;
  preview_key text;
  authors_payload jsonb := '[]'::jsonb;
  stocks_payload jsonb := '[]'::jsonb;
  cells_payload jsonb := '[]'::jsonb;
begin
  if coalesce(end_date_arg, '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
    requested_end := end_date_arg::date;
  end if;

  select preview.key_value
  into preview_key
  from (
    select
      se.security_key::text as key_value,
      max(sdv.date_key::date) as latest_date,
      count(*) as total_mentions
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
      and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
      and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
      and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
    group by se.security_key
    order by max(sdv.date_key::date) desc, count(*) desc
    limit 1
  ) preview;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    join public.account_domains ad on ad.account_id = xa.id and ad.domain = 'stock'
    where s.user_id = current_uid
      and s.domain = 'stock'
      and ad.status = 'approved'
  ),
  expanded as (
    select
      se.security_key::text as security_key,
      sdv.date_key::date as date_value,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
      and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
      and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
  )
  select max(e.date_value)
  into latest_visible_date
  from expanded e
  where e.author_name <> ''
    and (
      current_uid is not null
      or e.security_key = preview_key
    )
    and (
      current_uid is null
      or current_is_admin
      or e.author_name in (select va.author_name from visible_authors va)
    );

  if latest_visible_date is null then
    return jsonb_build_object(
      'start_date', null,
      'end_date', null,
      'previous_end_date', null,
      'next_end_date', null,
      'authors', authors_payload,
      'stocks', stocks_payload,
      'cells', cells_payload
    );
  end if;

  effective_end := case
    when requested_end is null or requested_end > latest_visible_date then latest_visible_date
    else requested_end
  end;
  effective_start := effective_end - 6;
  previous_end := effective_start - 1;
  next_end := case
    when effective_end < latest_visible_date then least(effective_end + 7, latest_visible_date)
    else null
  end;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    join public.account_domains ad on ad.account_id = xa.id and ad.domain = 'stock'
    where s.user_id = current_uid
      and s.domain = 'stock'
      and ad.status = 'approved'
  ),
  expanded as (
    select
      se.security_key::text as security_key,
      se.display_name::text as display_name,
      se.ticker::text as ticker,
      se.market::text as market,
      sdv.date_key::date as date_value,
      sdv.updated_at,
      view_item.value as view_value,
      view_item.ordinality,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name,
      coalesce(nullif(view_item.value ->> 'author_nickname', ''), view_item.value ->> 'display_name', view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', '') as author_nickname
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
    where sdv.date_key::date between effective_start and effective_end
      and coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
      and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
      and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
  ),
  scoped as (
    select *
    from expanded e
    where e.author_name <> ''
      and (
        current_uid is not null
        or e.security_key = preview_key
      )
      and (
        current_uid is null
        or current_is_admin
        or e.author_name in (select va.author_name from visible_authors va)
      )
  ),
  author_rows as (
    select
      author_name,
      (array_agg(author_nickname order by date_value desc, updated_at desc))[1] as author_nickname,
      count(*) as mention_count,
      max(date_value) as latest_date
    from scoped
    group by author_name
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'account_name', author_name,
        'author_nickname', author_nickname,
        'mention_count', mention_count,
        'latest_date', latest_date::text
      )
      order by mention_count desc, latest_date desc, author_name asc
    ),
    '[]'::jsonb
  )
  into authors_payload
  from author_rows;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    join public.account_domains ad on ad.account_id = xa.id and ad.domain = 'stock'
    where s.user_id = current_uid
      and s.domain = 'stock'
      and ad.status = 'approved'
  ),
  expanded as (
    select
      se.security_key::text as security_key,
      se.display_name::text as display_name,
      se.ticker::text as ticker,
      se.market::text as market,
      sdv.date_key::date as date_value,
      sdv.updated_at,
      view_item.value as view_value,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where sdv.date_key::date between effective_start and effective_end
      and coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
      and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
      and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
  ),
  scoped as (
    select *
    from expanded e
    where e.author_name <> ''
      and (
        current_uid is not null
        or e.security_key = preview_key
      )
      and (
        current_uid is null
        or current_is_admin
        or e.author_name in (select va.author_name from visible_authors va)
      )
  ),
  stock_rows as (
    select
      security_key,
      display_name,
      ticker,
      market,
      count(*) as mention_count,
      max(date_value) as latest_date
    from scoped
    group by security_key, display_name, ticker, market
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'security_key', security_key,
        'display_name', display_name,
        'ticker', ticker,
        'market', market,
        'mention_count', mention_count,
        'latest_date', latest_date::text
      )
      order by latest_date desc, mention_count desc, display_name asc
    ),
    '[]'::jsonb
  )
  into stocks_payload
  from stock_rows;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    join public.account_domains ad on ad.account_id = xa.id and ad.domain = 'stock'
    where s.user_id = current_uid
      and s.domain = 'stock'
      and ad.status = 'approved'
  ),
  expanded as (
    select
      se.security_key::text as security_key,
      sdv.date_key::date as date_value,
      sdv.updated_at,
      view_item.value as view_value,
      view_item.ordinality,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name,
      coalesce(nullif(view_item.value ->> 'author_nickname', ''), view_item.value ->> 'display_name', view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', '') as author_nickname
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
    where sdv.date_key::date between effective_start and effective_end
      and coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
      and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
      and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
  ),
  scoped as (
    select *
    from expanded e
    where e.author_name <> ''
      and (
        current_uid is not null
        or e.security_key = preview_key
      )
      and (
        current_uid is null
        or current_is_admin
        or e.author_name in (select va.author_name from visible_authors va)
      )
  ),
  cell_rows as (
    select
      security_key,
      author_name,
      max(author_nickname) as author_nickname,
      jsonb_agg(
        jsonb_build_object(
          'date', date_value::text,
          'platform', coalesce(view_value ->> 'platform', 'x'),
          'account_name', author_name,
          'author_nickname', coalesce(nullif(author_nickname, ''), author_name),
          'stance', coalesce(view_value ->> 'stance', 'unknown'),
          'direction', coalesce(view_value ->> 'direction', 'unknown'),
          'signal_type', coalesce(view_value ->> 'signal_type', 'unknown'),
          'judgment_type', coalesce(view_value ->> 'judgment_type', 'unknown'),
          'conviction', coalesce(view_value ->> 'conviction', 'unknown'),
          'evidence_type', coalesce(view_value ->> 'evidence_type', 'unknown'),
          'logic', coalesce(view_value ->> 'logic', ''),
          'evidence', coalesce(view_value -> 'evidence', '[]'::jsonb),
          'note_ids', coalesce(view_value -> 'note_ids', '[]'::jsonb),
          'note_urls', coalesce(view_value -> 'note_urls', '[]'::jsonb),
          'time_horizons', coalesce(view_value -> 'time_horizons', '[]'::jsonb)
        )
        order by date_value asc, ordinality asc
      ) as views
    from scoped
    group by security_key, author_name
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'security_key', security_key,
        'account_name', author_name,
        'author_nickname', coalesce(nullif(author_nickname, ''), author_name),
        'views', views
      )
      order by security_key asc, author_name asc
    ),
    '[]'::jsonb
  )
  into cells_payload
  from cell_rows;

  return jsonb_build_object(
    'start_date', effective_start::text,
    'end_date', effective_end::text,
    'previous_end_date', previous_end::text,
    'next_end_date', next_end::text,
    'authors', authors_payload,
    'stocks', stocks_payload,
    'cells', cells_payload
  );
end;
$$;

create or replace function public.list_visible_crypto_entities(
  query_arg text default '',
  limit_arg integer default 100,
  sort_arg text default 'date_desc'
)
returns table (
  entity_key text,
  display_name text,
  ticker text,
  market text,
  latest_date text,
  mention_days integer,
  total_mentions integer,
  updated_at timestamptz
)
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  safe_limit integer;
  safe_sort text;
begin
  safe_limit := case
    when current_uid is null then 1
    else least(greatest(coalesce(limit_arg, 100), 1), 500)
  end;
  safe_sort := case
    when coalesce(sort_arg, '') in ('date_desc', 'date_asc', 'count_desc', 'count_asc') then sort_arg
    else 'date_desc'
  end;

  return query
  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and s.domain = 'crypto'
  ),
  expanded as (
    select
      ce.asset_key::text as key_value,
      ce.display_name::text as display_value,
      ce.symbol::text as ticker_value,
      coalesce(ce.chain, ce.identifier_type)::text as market_value,
      cdv.date_key::text as date_value,
      cdv.updated_at,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name
    from public.crypto_entity_daily_views cdv
    join public.crypto_entities ce on ce.id = cdv.crypto_entity_id
    cross join lateral jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) as view_item(value)
  )
  select
    e.key_value,
    e.display_value,
    e.ticker_value,
    e.market_value,
    max(e.date_value)::text,
    count(distinct e.date_value)::integer,
    count(*)::integer,
    max(e.updated_at)
  from expanded e
  where e.author_name <> ''
    and (
      current_uid is null
      or current_is_admin
      or e.author_name in (select va.author_name from visible_authors va)
    )
    and (
      current_uid is null
      or coalesce(trim(query_arg), '') = ''
      or lower(e.key_value) like '%' || lower(trim(query_arg)) || '%'
      or lower(e.display_value) like '%' || lower(trim(query_arg)) || '%'
      or lower(coalesce(e.ticker_value, '')) like '%' || lower(trim(query_arg)) || '%'
      or lower(coalesce(e.market_value, '')) like '%' || lower(trim(query_arg)) || '%'
    )
  group by e.key_value, e.display_value, e.ticker_value, e.market_value
  order by
    case when safe_sort = 'date_desc' then max(e.date_value) end desc nulls last,
    case when safe_sort = 'date_asc' then max(e.date_value) end asc nulls last,
    case when safe_sort = 'count_desc' then count(*) end desc nulls last,
    case when safe_sort = 'count_asc' then count(*) end asc nulls last,
    e.display_value asc
  limit safe_limit;
end;
$$;

create or replace function public.get_visible_crypto_entity_timeline(
  entity_key_arg text,
  page_arg integer default 1,
  page_size_arg integer default 20
)
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  safe_page integer := greatest(coalesce(page_arg, 1), 1);
  safe_page_size integer;
  offset_value integer;
  preview_key text;
  total_count integer := 0;
  entity_id_value uuid;
  meta_payload jsonb;
  rows_payload jsonb;
begin
  safe_page_size := case
    when current_uid is null then least(greatest(coalesce(page_size_arg, 3), 1), 3)
    else least(greatest(coalesce(page_size_arg, 20), 1), 100)
  end;
  offset_value := (safe_page - 1) * safe_page_size;

  select preview.key_value
  into preview_key
  from (
    select
      ce.asset_key::text as key_value,
      max(cdv.date_key) as latest_date,
      count(*) as total_mentions
    from public.crypto_entity_daily_views cdv
    join public.crypto_entities ce on ce.id = cdv.crypto_entity_id
    cross join lateral jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
    group by ce.asset_key
    order by max(cdv.date_key) desc, count(*) desc
    limit 1
  ) preview;

  if current_uid is null and coalesce(entity_key_arg, '') <> coalesce(preview_key, '') then
    return null;
  end if;

  select
    ce.id,
    jsonb_build_object(
      'key', ce.asset_key,
      'display_name', ce.display_name,
      'ticker', ce.symbol,
      'market', coalesce(ce.chain, ce.identifier_type),
      'identifier_type', ce.identifier_type,
      'raw_identifiers', ce.raw_identifiers_json,
      'normalized_status', ce.normalized_status
    )
  into entity_id_value, meta_payload
  from public.crypto_entities ce
  where ce.asset_key = entity_key_arg
  limit 1;

  if meta_payload is null then
    return null;
  end if;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and s.domain = 'crypto'
  ),
  raw_days as (
    select
      cdv.date_key,
      cdv.updated_at,
      (
        select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
        from jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
        where lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
          and (
            current_uid is null
            or current_is_admin
            or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
              select va.author_name from visible_authors va
            )
          )
      ) as author_views
    from public.crypto_entity_daily_views cdv
    where cdv.crypto_entity_id = entity_id_value
  ),
  visible_days as (
    select *
    from raw_days
    where jsonb_array_length(author_views) > 0
  )
  select count(*)::integer
  into total_count
  from visible_days;

  if total_count = 0 then
    return null;
  end if;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and s.domain = 'crypto'
  ),
  raw_days as (
    select
      cdv.date_key,
      cdv.updated_at,
      (
        select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
        from jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
        where lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
          and (
            current_uid is null
            or current_is_admin
            or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
              select va.author_name from visible_authors va
            )
          )
      ) as author_views
    from public.crypto_entity_daily_views cdv
    where cdv.crypto_entity_id = entity_id_value
  ),
  visible_days as (
    select *
    from raw_days
    where jsonb_array_length(author_views) > 0
    order by date_key desc
    limit safe_page_size offset offset_value
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'date', date_key,
        'mention_count', jsonb_array_length(author_views),
        'author_views', author_views,
        'updated_at', updated_at
      )
      order by date_key desc
    ),
    '[]'::jsonb
  )
  into rows_payload
  from visible_days;

  return jsonb_build_object(
    'meta', meta_payload,
    'timeline', jsonb_build_object(
      'rows', rows_payload,
      'total', total_count,
      'page', safe_page,
      'page_size', safe_page_size,
      'total_pages', greatest(1, ceil(total_count::numeric / safe_page_size)::integer)
    )
  );
end;
$$;

create or replace function public.get_visible_crypto_matrix(
  end_date_arg text default null
)
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  requested_end date;
  latest_visible_date date;
  effective_end date;
  effective_start date;
  previous_end date;
  next_end date;
  preview_key text;
  authors_payload jsonb := '[]'::jsonb;
  assets_payload jsonb := '[]'::jsonb;
  cells_payload jsonb := '[]'::jsonb;
begin
  if coalesce(end_date_arg, '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
    requested_end := end_date_arg::date;
  end if;

  select preview.key_value
  into preview_key
  from (
    select
      ce.asset_key::text as key_value,
      max(cdv.date_key::date) as latest_date,
      count(*) as total_mentions
    from public.crypto_entity_daily_views cdv
    join public.crypto_entities ce on ce.id = cdv.crypto_entity_id
    cross join lateral jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
    group by ce.asset_key
    order by max(cdv.date_key::date) desc, count(*) desc
    limit 1
  ) preview;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and s.domain = 'crypto'
  ),
  expanded as (
    select
      ce.asset_key::text as asset_key,
      cdv.date_key::date as date_value,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name
    from public.crypto_entity_daily_views cdv
    join public.crypto_entities ce on ce.id = cdv.crypto_entity_id
    cross join lateral jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) as view_item(value)
  )
  select max(e.date_value)
  into latest_visible_date
  from expanded e
  where e.author_name <> ''
    and (
      current_uid is not null
      or e.asset_key = preview_key
    )
    and (
      current_uid is null
      or current_is_admin
      or e.author_name in (select va.author_name from visible_authors va)
    );

  if latest_visible_date is null then
    return jsonb_build_object(
      'start_date', null,
      'end_date', null,
      'previous_end_date', null,
      'next_end_date', null,
      'authors', authors_payload,
      'assets', assets_payload,
      'cells', cells_payload
    );
  end if;

  effective_end := case
    when requested_end is null or requested_end > latest_visible_date then latest_visible_date
    else requested_end
  end;
  effective_start := effective_end - 6;
  previous_end := effective_start - 1;
  next_end := case
    when effective_end < latest_visible_date then least(effective_end + 7, latest_visible_date)
    else null
  end;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and s.domain = 'crypto'
  ),
  expanded as (
    select
      ce.asset_key::text as asset_key,
      ce.display_name::text as display_name,
      ce.symbol::text as symbol,
      coalesce(ce.chain, ce.identifier_type)::text as market,
      cdv.date_key::date as date_value,
      cdv.updated_at,
      view_item.value as view_value,
      view_item.ordinality,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name,
      coalesce(nullif(view_item.value ->> 'author_nickname', ''), view_item.value ->> 'display_name', view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', '') as author_nickname
    from public.crypto_entity_daily_views cdv
    join public.crypto_entities ce on ce.id = cdv.crypto_entity_id
    cross join lateral jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
    where cdv.date_key::date between effective_start and effective_end
  ),
  scoped as (
    select *
    from expanded e
    where e.author_name <> ''
      and (
        current_uid is not null
        or e.asset_key = preview_key
      )
      and (
        current_uid is null
        or current_is_admin
        or e.author_name in (select va.author_name from visible_authors va)
      )
  ),
  author_rows as (
    select
      author_name,
      (array_agg(author_nickname order by date_value desc, updated_at desc))[1] as author_nickname,
      count(*) as mention_count,
      max(date_value) as latest_date
    from scoped
    group by author_name
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'account_name', author_name,
        'author_nickname', author_nickname,
        'mention_count', mention_count,
        'latest_date', latest_date::text
      )
      order by mention_count desc, latest_date desc, author_name asc
    ),
    '[]'::jsonb
  )
  into authors_payload
  from author_rows;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and s.domain = 'crypto'
  ),
  expanded as (
    select
      ce.asset_key::text as asset_key,
      ce.display_name::text as display_name,
      ce.symbol::text as symbol,
      coalesce(ce.chain, ce.identifier_type)::text as market,
      cdv.date_key::date as date_value,
      cdv.updated_at,
      view_item.value as view_value,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name
    from public.crypto_entity_daily_views cdv
    join public.crypto_entities ce on ce.id = cdv.crypto_entity_id
    cross join lateral jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where cdv.date_key::date between effective_start and effective_end
  ),
  scoped as (
    select *
    from expanded e
    where e.author_name <> ''
      and (
        current_uid is not null
        or e.asset_key = preview_key
      )
      and (
        current_uid is null
        or current_is_admin
        or e.author_name in (select va.author_name from visible_authors va)
      )
  ),
  asset_rows as (
    select
      asset_key,
      display_name,
      symbol,
      market,
      count(*) as mention_count,
      max(date_value) as latest_date
    from scoped
    group by asset_key, display_name, symbol, market
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'asset_key', asset_key,
        'display_name', display_name,
        'ticker', symbol,
        'market', market,
        'mention_count', mention_count,
        'latest_date', latest_date::text
      )
      order by latest_date desc, mention_count desc, display_name asc
    ),
    '[]'::jsonb
  )
  into assets_payload
  from asset_rows;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and s.domain = 'crypto'
  ),
  expanded as (
    select
      ce.asset_key::text as asset_key,
      cdv.date_key::date as date_value,
      cdv.updated_at,
      view_item.value as view_value,
      view_item.ordinality,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name,
      coalesce(nullif(view_item.value ->> 'author_nickname', ''), view_item.value ->> 'display_name', view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', '') as author_nickname
    from public.crypto_entity_daily_views cdv
    join public.crypto_entities ce on ce.id = cdv.crypto_entity_id
    cross join lateral jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
    where cdv.date_key::date between effective_start and effective_end
  ),
  scoped as (
    select *
    from expanded e
    where e.author_name <> ''
      and (
        current_uid is not null
        or e.asset_key = preview_key
      )
      and (
        current_uid is null
        or current_is_admin
        or e.author_name in (select va.author_name from visible_authors va)
      )
  ),
  cell_rows as (
    select
      asset_key,
      author_name,
      max(author_nickname) as author_nickname,
      jsonb_agg(
        jsonb_build_object(
          'date', date_value::text,
          'platform', coalesce(view_value ->> 'platform', 'x'),
          'account_name', author_name,
          'author_nickname', coalesce(nullif(author_nickname, ''), author_name),
          'stance', coalesce(view_value ->> 'stance', 'unknown'),
          'direction', coalesce(view_value ->> 'direction', 'unknown'),
          'signal_type', coalesce(view_value ->> 'signal_type', 'unknown'),
          'judgment_type', coalesce(view_value ->> 'judgment_type', 'unknown'),
          'conviction', coalesce(view_value ->> 'conviction', 'unknown'),
          'evidence_type', coalesce(view_value ->> 'evidence_type', 'unknown'),
          'logic', coalesce(view_value ->> 'logic', ''),
          'evidence', coalesce(view_value -> 'evidence', '[]'::jsonb),
          'note_ids', coalesce(view_value -> 'note_ids', '[]'::jsonb),
          'note_urls', coalesce(view_value -> 'note_urls', '[]'::jsonb),
          'time_horizons', coalesce(view_value -> 'time_horizons', '[]'::jsonb),
          'metadata', coalesce(view_value -> 'metadata', '{}'::jsonb)
        )
        order by date_value asc, ordinality asc
      ) as views
    from scoped
    group by asset_key, author_name
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'asset_key', asset_key,
        'account_name', author_name,
        'author_nickname', coalesce(nullif(author_nickname, ''), author_name),
        'views', views
      )
      order by asset_key asc, author_name asc
    ),
    '[]'::jsonb
  )
  into cells_payload
  from cell_rows;

  return jsonb_build_object(
    'start_date', effective_start::text,
    'end_date', effective_end::text,
    'previous_end_date', previous_end::text,
    'next_end_date', next_end::text,
    'authors', authors_payload,
    'assets', assets_payload,
    'cells', cells_payload
  );
end;
$$;

revoke all on function public.list_public_accounts(text, integer) from public;
revoke all on function public.list_public_accounts(text, integer, text) from public;
revoke all on function public.submit_x_account(text, text) from public;
revoke all on function public.submit_x_account(text, text, text) from public;
revoke all on function public.approve_account_request(uuid) from public;
revoke all on function public.reject_account_request(uuid) from public;
revoke all on function public.disable_x_account(uuid) from public;
revoke all on function public.disable_x_account(uuid, text) from public;
revoke all on function public.enqueue_manual_crawl() from public;
revoke all on function public.enqueue_manual_crawl(text) from public;
revoke all on function public.list_visible_authors(text, integer) from public;
revoke all on function public.list_visible_authors(text, integer, text) from public;
revoke all on function public.get_visible_author_timeline(uuid, integer, integer) from public;
revoke all on function public.get_visible_author_timeline(uuid, integer, integer, text) from public;
revoke all on function public.list_visible_entities(text, text, integer) from public;
revoke all on function public.list_visible_entities(text, text, integer, text) from public;
revoke all on function public.get_visible_entity_timeline(text, text, integer, integer) from public;
revoke all on function public.get_visible_stock_matrix(text) from public;
revoke all on function public.list_visible_crypto_entities(text, integer, text) from public;
revoke all on function public.get_visible_crypto_entity_timeline(text, integer, integer) from public;
revoke all on function public.get_visible_crypto_matrix(text) from public;

grant execute on function public.list_public_accounts(text, integer) to anon, authenticated;
grant execute on function public.list_public_accounts(text, integer, text) to anon, authenticated;
grant execute on function public.submit_x_account(text, text) to authenticated;
grant execute on function public.submit_x_account(text, text, text) to authenticated;
grant execute on function public.approve_account_request(uuid) to authenticated;
grant execute on function public.reject_account_request(uuid) to authenticated;
grant execute on function public.disable_x_account(uuid) to authenticated;
grant execute on function public.disable_x_account(uuid, text) to authenticated;
grant execute on function public.enqueue_manual_crawl() to authenticated;
grant execute on function public.enqueue_manual_crawl(text) to authenticated;
grant execute on function public.list_visible_authors(text, integer) to anon, authenticated;
grant execute on function public.list_visible_authors(text, integer, text) to anon, authenticated;
grant execute on function public.get_visible_author_timeline(uuid, integer, integer) to anon, authenticated;
grant execute on function public.get_visible_author_timeline(uuid, integer, integer, text) to anon, authenticated;
grant execute on function public.list_visible_entities(text, text, integer) to anon, authenticated;
grant execute on function public.list_visible_entities(text, text, integer, text) to anon, authenticated;
grant execute on function public.get_visible_entity_timeline(text, text, integer, integer) to anon, authenticated;
grant execute on function public.get_visible_stock_matrix(text) to anon, authenticated;
grant execute on function public.list_visible_crypto_entities(text, integer, text) to anon, authenticated;
grant execute on function public.get_visible_crypto_entity_timeline(text, integer, integer) to anon, authenticated;
grant execute on function public.get_visible_crypto_matrix(text) to anon, authenticated;
