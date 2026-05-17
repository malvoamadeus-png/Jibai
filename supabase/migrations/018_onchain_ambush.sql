-- Add on-chain wallet tracking surfaces for the onchain ambush board.

create table if not exists public.onchain_wallets (
  id uuid primary key default gen_random_uuid(),
  address text not null unique,
  address_kind text not null default 'evm'
    check (address_kind in ('evm', 'solana', 'unknown')),
  admin_label text not null default '',
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'rejected', 'disabled')),
  submitted_by uuid references public.profiles(id) on delete set null,
  approved_by uuid references public.profiles(id) on delete set null,
  approved_at timestamptz,
  rejected_at timestamptz,
  disabled_at timestamptz,
  last_snapshot_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.onchain_wallet_chains (
  wallet_id uuid not null references public.onchain_wallets(id) on delete cascade,
  chain_key text not null check (chain_key in ('ethereum', 'base', 'bsc', 'solana')),
  chain_index text not null,
  enabled boolean not null default true,
  updated_at timestamptz not null default now(),
  primary key(wallet_id, chain_key)
);

create table if not exists public.onchain_wallet_requests (
  id uuid primary key default gen_random_uuid(),
  wallet_id uuid not null references public.onchain_wallets(id) on delete cascade,
  requester_id uuid not null references public.profiles(id) on delete cascade,
  raw_input text not null,
  normalized_address text not null,
  requested_chains_json jsonb not null default '[]'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'rejected')),
  review_note text not null default '',
  reviewed_by uuid references public.profiles(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(wallet_id, requester_id)
);

create table if not exists public.onchain_user_wallet_subscriptions (
  user_id uuid not null references public.profiles(id) on delete cascade,
  wallet_id uuid not null references public.onchain_wallets(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key(user_id, wallet_id)
);

create table if not exists public.onchain_user_wallet_notes (
  user_id uuid not null references public.profiles(id) on delete cascade,
  wallet_id uuid not null references public.onchain_wallets(id) on delete cascade,
  note text not null default '',
  updated_at timestamptz not null default now(),
  primary key(user_id, wallet_id)
);

create table if not exists public.onchain_tokens (
  id uuid primary key default gen_random_uuid(),
  token_key text not null unique,
  chain_key text not null check (chain_key in ('ethereum', 'base', 'bsc', 'solana')),
  chain_index text not null,
  token_contract_address text not null default '',
  symbol text not null default '',
  display_name text not null default '',
  is_native boolean not null default false,
  is_risk_token boolean not null default false,
  filter_reason text not null default '',
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.onchain_fetch_runs (
  id uuid primary key default gen_random_uuid(),
  kind text not null default 'manual'
    check (kind in ('manual', 'scheduled', 'once', 'rebuild')),
  status text not null default 'pending'
    check (status in ('pending', 'running', 'succeeded', 'failed', 'partial')),
  requested_by uuid references public.profiles(id) on delete set null,
  started_at timestamptz,
  finished_at timestamptz,
  summary text not null default '',
  error_text text,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.onchain_fetch_runs
  drop constraint if exists onchain_fetch_runs_status_check;

alter table public.onchain_fetch_runs
  add constraint onchain_fetch_runs_status_check
  check (status in ('pending', 'running', 'succeeded', 'failed', 'partial'));

create table if not exists public.onchain_fetch_run_items (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.onchain_fetch_runs(id) on delete cascade,
  wallet_id uuid not null references public.onchain_wallets(id) on delete cascade,
  chain_key text not null check (chain_key in ('ethereum', 'base', 'bsc', 'solana')),
  chain_index text not null,
  status text not null
    check (status in ('success', 'empty', 'api_error', 'rate_limited', 'auth_error', 'network_error', 'partial')),
  token_count integer not null default 0,
  visible_token_count integer not null default 0,
  error_text text,
  created_at timestamptz not null default now()
);

create table if not exists public.onchain_balance_snapshots (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.onchain_fetch_runs(id) on delete cascade,
  wallet_id uuid not null references public.onchain_wallets(id) on delete cascade,
  token_id uuid not null references public.onchain_tokens(id) on delete cascade,
  chain_key text not null check (chain_key in ('ethereum', 'base', 'bsc', 'solana')),
  chain_index text not null,
  date_key text not null,
  snapshot_at timestamptz not null default now(),
  balance numeric not null default 0,
  raw_balance numeric not null default 0,
  token_price_usd numeric not null default 0,
  holding_value_usd numeric not null default 0,
  is_risk_token boolean not null default false,
  excluded boolean not null default false,
  exclusion_reason text not null default '',
  created_at timestamptz not null default now()
);

create table if not exists public.onchain_daily_wallet_token_views (
  id uuid primary key default gen_random_uuid(),
  date_key text not null,
  wallet_id uuid not null references public.onchain_wallets(id) on delete cascade,
  token_id uuid not null references public.onchain_tokens(id) on delete cascade,
  chain_key text not null check (chain_key in ('ethereum', 'base', 'bsc', 'solana')),
  chain_index text not null,
  snapshot_at timestamptz not null,
  balance numeric not null default 0,
  token_price_usd numeric not null default 0,
  holding_value_usd numeric not null default 0,
  previous_balance numeric,
  previous_value_usd numeric,
  balance_delta numeric,
  value_usd_delta numeric,
  state text not null default 'held'
    check (state in ('new', 'held', 'increased', 'decreased', 'exited', 'below_threshold')),
  updated_at timestamptz not null default now(),
  unique(date_key, wallet_id, token_id)
);

create table if not exists public.onchain_daily_token_views (
  id uuid primary key default gen_random_uuid(),
  date_key text not null,
  token_id uuid not null references public.onchain_tokens(id) on delete cascade,
  chain_key text not null check (chain_key in ('ethereum', 'base', 'bsc', 'solana')),
  chain_index text not null,
  holder_count integer not null default 0,
  balance_sum numeric not null default 0,
  value_usd_sum numeric not null default 0,
  holder_count_delta integer,
  balance_delta numeric,
  value_usd_delta numeric,
  new_holder_count integer not null default 0,
  exited_holder_count integer not null default 0,
  holders_json jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now(),
  unique(date_key, token_id)
);

create table if not exists public.onchain_token_filter_rules (
  id uuid primary key default gen_random_uuid(),
  rule_type text not null check (rule_type in ('stablecoin', 'core_asset', 'risk_token', 'custom')),
  chain_index text,
  token_contract_address text,
  symbol text,
  enabled boolean not null default true,
  note text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_onchain_wallets_status
  on public.onchain_wallets(status, updated_at desc);
create index if not exists idx_onchain_wallet_chains_enabled
  on public.onchain_wallet_chains(chain_key, enabled);
create index if not exists idx_onchain_wallet_requests_status
  on public.onchain_wallet_requests(status, created_at);
create index if not exists idx_onchain_tokens_chain_symbol
  on public.onchain_tokens(chain_key, symbol);
create index if not exists idx_onchain_fetch_runs_status
  on public.onchain_fetch_runs(status, created_at);
create index if not exists idx_onchain_snapshots_run
  on public.onchain_balance_snapshots(run_id, wallet_id, chain_key);
create index if not exists idx_onchain_snapshots_date_wallet
  on public.onchain_balance_snapshots(date_key, wallet_id, token_id, snapshot_at desc);
create index if not exists idx_onchain_daily_wallet_date
  on public.onchain_daily_wallet_token_views(date_key, wallet_id, token_id);
create index if not exists idx_onchain_daily_token_date
  on public.onchain_daily_token_views(date_key desc, token_id);
create unique index if not exists onchain_filter_rules_unique
  on public.onchain_token_filter_rules (
    rule_type,
    coalesce(chain_index, ''),
    coalesce(token_contract_address, ''),
    coalesce(symbol, '')
  );

drop trigger if exists set_onchain_wallets_updated_at on public.onchain_wallets;
create trigger set_onchain_wallets_updated_at before update on public.onchain_wallets
for each row execute function public.set_updated_at();

drop trigger if exists set_onchain_wallet_requests_updated_at on public.onchain_wallet_requests;
create trigger set_onchain_wallet_requests_updated_at before update on public.onchain_wallet_requests
for each row execute function public.set_updated_at();

drop trigger if exists set_onchain_user_wallet_notes_updated_at on public.onchain_user_wallet_notes;
create trigger set_onchain_user_wallet_notes_updated_at before update on public.onchain_user_wallet_notes
for each row execute function public.set_updated_at();

drop trigger if exists set_onchain_tokens_updated_at on public.onchain_tokens;
create trigger set_onchain_tokens_updated_at before update on public.onchain_tokens
for each row execute function public.set_updated_at();

drop trigger if exists set_onchain_fetch_runs_updated_at on public.onchain_fetch_runs;
create trigger set_onchain_fetch_runs_updated_at before update on public.onchain_fetch_runs
for each row execute function public.set_updated_at();

drop trigger if exists set_onchain_filter_rules_updated_at on public.onchain_token_filter_rules;
create trigger set_onchain_filter_rules_updated_at before update on public.onchain_token_filter_rules
for each row execute function public.set_updated_at();

alter table public.onchain_wallets enable row level security;
alter table public.onchain_wallet_chains enable row level security;
alter table public.onchain_wallet_requests enable row level security;
alter table public.onchain_user_wallet_subscriptions enable row level security;
alter table public.onchain_user_wallet_notes enable row level security;
alter table public.onchain_tokens enable row level security;
alter table public.onchain_fetch_runs enable row level security;
alter table public.onchain_fetch_run_items enable row level security;
alter table public.onchain_balance_snapshots enable row level security;
alter table public.onchain_daily_wallet_token_views enable row level security;
alter table public.onchain_daily_token_views enable row level security;
alter table public.onchain_token_filter_rules enable row level security;

drop policy if exists "onchain wallets public read" on public.onchain_wallets;
create policy "onchain wallets public read" on public.onchain_wallets
for select to anon, authenticated using (status = 'approved' or public.is_current_user_admin());

drop policy if exists "onchain chains public read" on public.onchain_wallet_chains;
create policy "onchain chains public read" on public.onchain_wallet_chains
for select to anon, authenticated using (
  exists (
    select 1 from public.onchain_wallets w
    where w.id = onchain_wallet_chains.wallet_id
      and (w.status = 'approved' or public.is_current_user_admin())
  )
);

drop policy if exists "onchain requests user read" on public.onchain_wallet_requests;
create policy "onchain requests user read" on public.onchain_wallet_requests
for select to authenticated using (requester_id = auth.uid() or public.is_current_user_admin());

drop policy if exists "onchain subscriptions user read" on public.onchain_user_wallet_subscriptions;
create policy "onchain subscriptions user read" on public.onchain_user_wallet_subscriptions
for select to authenticated using (user_id = auth.uid() or public.is_current_user_admin());

drop policy if exists "onchain subscriptions user write" on public.onchain_user_wallet_subscriptions;
create policy "onchain subscriptions user write" on public.onchain_user_wallet_subscriptions
for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "onchain notes user read" on public.onchain_user_wallet_notes;
create policy "onchain notes user read" on public.onchain_user_wallet_notes
for select to authenticated using (user_id = auth.uid() or public.is_current_user_admin());

drop policy if exists "onchain notes user write" on public.onchain_user_wallet_notes;
create policy "onchain notes user write" on public.onchain_user_wallet_notes
for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "onchain tokens public read" on public.onchain_tokens;
create policy "onchain tokens public read" on public.onchain_tokens
for select to anon, authenticated using (true);

drop policy if exists "onchain daily token public read" on public.onchain_daily_token_views;
create policy "onchain daily token public read" on public.onchain_daily_token_views
for select to anon, authenticated using (true);

drop policy if exists "onchain admin fetch runs read" on public.onchain_fetch_runs;
create policy "onchain admin fetch runs read" on public.onchain_fetch_runs
for select to anon, authenticated using (
  public.is_current_user_admin()
  or status in ('succeeded', 'failed', 'running')
);

drop policy if exists "onchain admin fetch items read" on public.onchain_fetch_run_items;
create policy "onchain admin fetch items read" on public.onchain_fetch_run_items
for select to authenticated using (public.is_current_user_admin());

drop policy if exists "onchain admin snapshots read" on public.onchain_balance_snapshots;
create policy "onchain admin snapshots read" on public.onchain_balance_snapshots
for select to authenticated using (public.is_current_user_admin());

drop policy if exists "onchain daily wallet admin read" on public.onchain_daily_wallet_token_views;
create policy "onchain daily wallet admin read" on public.onchain_daily_wallet_token_views
for select to authenticated using (
  public.is_current_user_admin()
  or exists (
    select 1
    from public.onchain_user_wallet_subscriptions s
    where s.user_id = auth.uid()
      and s.wallet_id = onchain_daily_wallet_token_views.wallet_id
  )
);

drop policy if exists "onchain filter admin read" on public.onchain_token_filter_rules;
create policy "onchain filter admin read" on public.onchain_token_filter_rules
for select to authenticated using (public.is_current_user_admin());

create or replace function public.onchain_normalize_address(value_arg text)
returns text
language sql
immutable
as $$
  select case
    when value_arg ~* '^0x[0-9a-f]{40}$' then lower(value_arg)
    else trim(value_arg)
  end;
$$;

create or replace function public.onchain_short_address(value_arg text)
returns text
language sql
immutable
as $$
  select case
    when length(coalesce(value_arg, '')) <= 14 then coalesce(value_arg, '')
    else left(value_arg, 6) || '...' || right(value_arg, 4)
  end;
$$;

create or replace function public.onchain_chain_index(chain_key_arg text)
returns text
language sql
immutable
as $$
  select case chain_key_arg
    when 'ethereum' then '1'
    when 'base' then '8453'
    when 'bsc' then '56'
    when 'solana' then '501'
    else ''
  end;
$$;

create or replace function public.onchain_visible_wallet_ids()
returns table(wallet_id uuid)
language sql
security definer
set search_path = public
as $$
  select w.id
  from public.onchain_wallets w
  where w.status = 'approved'
    and (
      public.is_current_user_admin()
      or (
        auth.uid() is not null
        and exists (
          select 1
          from public.onchain_user_wallet_subscriptions s
          where s.user_id = auth.uid()
            and s.wallet_id = w.id
        )
      )
      or (
        auth.uid() is null
        and w.id in (
          select id
          from public.onchain_wallets
          where status = 'approved'
          order by coalesce(approved_at, updated_at, created_at) asc
          limit 2
        )
      )
    );
$$;

create or replace function public.list_onchain_wallets(query_arg text, limit_arg integer)
returns table (
  id uuid,
  address text,
  address_short text,
  display_name text,
  admin_label text,
  user_note text,
  subscribed boolean,
  enabled_chains jsonb,
  last_snapshot_at timestamptz,
  status text
)
language sql
security definer
set search_path = public
as $$
  select
    w.id,
    w.address,
    public.onchain_short_address(w.address) as address_short,
    coalesce(nullif(n.note, ''), nullif(w.admin_label, ''), public.onchain_short_address(w.address)) as display_name,
    w.admin_label,
    coalesce(n.note, '') as user_note,
    exists (
      select 1
      from public.onchain_user_wallet_subscriptions s
      where s.user_id = auth.uid()
        and s.wallet_id = w.id
    ) as subscribed,
    coalesce(
      (
        select jsonb_agg(
          jsonb_build_object('key', c.chain_key, 'chainIndex', c.chain_index, 'enabled', c.enabled)
          order by c.chain_key
        )
        from public.onchain_wallet_chains c
        where c.wallet_id = w.id and c.enabled
      ),
      '[]'::jsonb
    ) as enabled_chains,
    w.last_snapshot_at,
    w.status
  from public.onchain_wallets w
  left join public.onchain_user_wallet_notes n on n.wallet_id = w.id and n.user_id = auth.uid()
  where w.status = 'approved'
    and (
      coalesce(query_arg, '') = ''
      or w.address ilike '%' || query_arg || '%'
      or w.admin_label ilike '%' || query_arg || '%'
      or n.note ilike '%' || query_arg || '%'
    )
  order by coalesce(w.last_snapshot_at, w.approved_at, w.updated_at, w.created_at) desc, w.address asc
  limit case
    when auth.uid() is null then 2
    else greatest(1, least(coalesce(limit_arg, 100), 200))
  end;
$$;

create or replace function public.submit_onchain_wallet(raw_input_arg text, chain_keys_arg text[] default '{}'::text[])
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  normalized text;
  wallet_id_value uuid;
  request_status text;
begin
  if auth.uid() is null then
    raise exception 'Authentication required.';
  end if;

  normalized := public.onchain_normalize_address(trim(raw_input_arg));
  if normalized = '' then
    raise exception 'Wallet address is required.';
  end if;

  insert into public.onchain_wallets (address, address_kind, status, submitted_by)
  values (
    normalized,
    case when normalized ~ '^0x[0-9a-f]{40}$' then 'evm' else 'unknown' end,
    'pending',
    auth.uid()
  )
  on conflict (address) do update set updated_at = public.onchain_wallets.updated_at
  returning id into wallet_id_value;

  select case when status = 'approved' then 'approved' else 'pending' end
  into request_status
  from public.onchain_wallets
  where id = wallet_id_value;

  insert into public.onchain_wallet_requests (
    wallet_id, requester_id, raw_input, normalized_address, requested_chains_json,
    status, reviewed_by, reviewed_at
  )
  values (
    wallet_id_value,
    auth.uid(),
    raw_input_arg,
    normalized,
    to_jsonb(coalesce(chain_keys_arg, '{}'::text[])),
    request_status,
    case when request_status = 'approved' then auth.uid() else null end,
    case when request_status = 'approved' then now() else null end
  )
  on conflict (wallet_id, requester_id) do update set
    raw_input = excluded.raw_input,
    requested_chains_json = excluded.requested_chains_json,
    status = excluded.status,
    updated_at = now();

  if request_status = 'approved' then
    insert into public.onchain_user_wallet_subscriptions (user_id, wallet_id)
    values (auth.uid(), wallet_id_value)
    on conflict do nothing;
  end if;

  return wallet_id_value;
end;
$$;

create or replace function public.set_onchain_wallet_subscription(wallet_id_arg uuid, subscribed_arg boolean)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.uid() is null then
    raise exception 'Authentication required.';
  end if;
  if not exists (
    select 1 from public.onchain_wallets
    where id = wallet_id_arg and status = 'approved'
  ) then
    raise exception 'Wallet is not approved.';
  end if;

  if subscribed_arg then
    insert into public.onchain_user_wallet_subscriptions (user_id, wallet_id)
    values (auth.uid(), wallet_id_arg)
    on conflict do nothing;
  else
    delete from public.onchain_user_wallet_subscriptions
    where user_id = auth.uid() and wallet_id = wallet_id_arg;
  end if;
end;
$$;

create or replace function public.set_onchain_wallet_note(wallet_id_arg uuid, note_arg text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.uid() is null then
    raise exception 'Authentication required.';
  end if;
  if length(trim(coalesce(note_arg, ''))) = 0 then
    delete from public.onchain_user_wallet_notes
    where user_id = auth.uid() and wallet_id = wallet_id_arg;
    return;
  end if;
  insert into public.onchain_user_wallet_notes (user_id, wallet_id, note)
  values (auth.uid(), wallet_id_arg, left(trim(note_arg), 80))
  on conflict (user_id, wallet_id) do update set
    note = excluded.note,
    updated_at = now();
end;
$$;

create or replace function public.approve_onchain_wallet_request(request_id_arg uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  wallet_id_value uuid;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin privileges required.';
  end if;

  select wallet_id into wallet_id_value
  from public.onchain_wallet_requests
  where id = request_id_arg;
  if wallet_id_value is null then
    raise exception 'Request not found.';
  end if;

  update public.onchain_wallet_requests
  set status = 'approved', reviewed_by = auth.uid(), reviewed_at = now(), updated_at = now()
  where id = request_id_arg;

  update public.onchain_wallets
  set status = 'approved',
      approved_by = auth.uid(),
      approved_at = coalesce(approved_at, now()),
      rejected_at = null,
      disabled_at = null,
      updated_at = now()
  where id = wallet_id_value;

  insert into public.onchain_user_wallet_subscriptions (user_id, wallet_id)
  select requester_id, wallet_id
  from public.onchain_wallet_requests
  where id = request_id_arg
  on conflict do nothing;
end;
$$;

create or replace function public.reject_onchain_wallet_request(request_id_arg uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin privileges required.';
  end if;
  update public.onchain_wallet_requests
  set status = 'rejected', reviewed_by = auth.uid(), reviewed_at = now(), updated_at = now()
  where id = request_id_arg;
end;
$$;

create or replace function public.admin_update_onchain_wallet(
  wallet_id_arg uuid,
  admin_label_arg text,
  chain_keys_arg text[],
  status_arg text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  chain_key_value text;
  safe_status text;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin privileges required.';
  end if;

  safe_status := case
    when status_arg in ('pending', 'approved', 'rejected', 'disabled') then status_arg
    else 'approved'
  end;

  update public.onchain_wallets
  set admin_label = left(trim(coalesce(admin_label_arg, '')), 80),
      status = safe_status,
      approved_at = case when safe_status = 'approved' then coalesce(approved_at, now()) else approved_at end,
      rejected_at = case when safe_status = 'rejected' then now() else null end,
      disabled_at = case when safe_status = 'disabled' then now() else null end,
      updated_at = now()
  where id = wallet_id_arg;

  update public.onchain_wallet_chains
  set enabled = false, updated_at = now()
  where wallet_id = wallet_id_arg;

  foreach chain_key_value in array coalesce(chain_keys_arg, '{}'::text[]) loop
    if public.onchain_chain_index(chain_key_value) <> '' then
      insert into public.onchain_wallet_chains (wallet_id, chain_key, chain_index, enabled)
      values (wallet_id_arg, chain_key_value, public.onchain_chain_index(chain_key_value), true)
      on conflict (wallet_id, chain_key) do update set
        chain_index = excluded.chain_index,
        enabled = true,
        updated_at = now();
    end if;
  end loop;

  if safe_status <> 'approved' then
    delete from public.onchain_user_wallet_subscriptions
    where wallet_id = wallet_id_arg;
  end if;
end;
$$;

create or replace function public.enqueue_onchain_fetch()
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  run_id_value uuid;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin privileges required.';
  end if;
  insert into public.onchain_fetch_runs (kind, status, requested_by, metadata_json)
  values ('manual', 'pending', auth.uid(), jsonb_build_object('source', 'admin'))
  returning id into run_id_value;
  return run_id_value;
end;
$$;

create or replace function public.list_my_onchain_wallet_requests()
returns table (
  id uuid,
  status text,
  raw_input text,
  normalized_address text,
  created_at timestamptz
)
language sql
security definer
set search_path = public
as $$
  select id, status, raw_input, normalized_address, created_at
  from public.onchain_wallet_requests
  where requester_id = auth.uid()
  order by created_at desc
  limit 30;
$$;

create or replace function public.get_onchain_token_matrix(
  end_date_arg text default null,
  chain_keys_arg text[] default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  payload jsonb;
begin
  with visible_wallets as (
    select wallet_id from public.onchain_visible_wallet_ids()
  ),
  available_dates as (
    select distinct d.date_key
    from public.onchain_daily_wallet_token_views d
    join visible_wallets vw on vw.wallet_id = d.wallet_id
    where (chain_keys_arg is null or cardinality(chain_keys_arg) = 0 or d.chain_key = any(chain_keys_arg))
      and (end_date_arg is null or d.date_key <= end_date_arg)
    order by d.date_key desc
    limit 7
  ),
  dates as (
    select date_key from available_dates order by date_key asc
  ),
  aggregate_rows as (
    select
      d.date_key,
      t.id as token_id,
      t.token_key,
      t.chain_key,
      t.chain_index,
      t.token_contract_address,
      t.symbol,
      coalesce(nullif(t.display_name, ''), nullif(t.symbol, ''), public.onchain_short_address(t.token_contract_address)) as display_name,
      count(distinct d.wallet_id)::int as holder_count,
      coalesce(sum(d.balance), 0) as balance_sum,
      coalesce(sum(d.holding_value_usd), 0) as value_usd_sum,
      jsonb_agg(
        jsonb_build_object(
          'walletId', w.id,
          'address', w.address,
          'addressShort', public.onchain_short_address(w.address),
          'displayName', coalesce(nullif(n.note, ''), nullif(w.admin_label, ''), public.onchain_short_address(w.address)),
          'balance', d.balance,
          'valueUsd', d.holding_value_usd
        )
        order by d.holding_value_usd desc
      ) as holders
    from public.onchain_daily_wallet_token_views d
    join dates on dates.date_key = d.date_key
    join visible_wallets vw on vw.wallet_id = d.wallet_id
    join public.onchain_tokens t on t.id = d.token_id
    join public.onchain_wallets w on w.id = d.wallet_id
    left join public.onchain_user_wallet_notes n on n.wallet_id = w.id and n.user_id = auth.uid()
    where chain_keys_arg is null or cardinality(chain_keys_arg) = 0 or d.chain_key = any(chain_keys_arg)
    group by d.date_key, t.id
  ),
  aggregate_with_prev as (
    select
      a.*,
      lag(a.holder_count) over (partition by a.token_id order by a.date_key) as previous_holder_count,
      lag(a.balance_sum) over (partition by a.token_id order by a.date_key) as previous_balance_sum,
      lag(a.value_usd_sum) over (partition by a.token_id order by a.date_key) as previous_value_usd_sum
    from aggregate_rows a
  ),
  token_rows as (
    select
      token_id,
      token_key,
      chain_key,
      chain_index,
      token_contract_address,
      symbol,
      display_name,
      max(date_key) as latest_date,
      max(holder_count) as latest_holder_count,
      max(value_usd_sum) as latest_value_usd
    from aggregate_with_prev
    group by token_id, token_key, chain_key, chain_index, token_contract_address, symbol, display_name
    order by max(date_key) desc, max(holder_count) desc, max(value_usd_sum) desc, display_name asc
    limit 100
  )
  select jsonb_build_object(
    'dates', coalesce((select jsonb_agg(date_key order by date_key) from dates), '[]'::jsonb),
    'tokens', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'tokenId', token_id,
          'tokenKey', token_key,
          'chainKey', chain_key,
          'chainIndex', chain_index,
          'contractAddress', token_contract_address,
          'symbol', symbol,
          'displayName', display_name,
          'latestDate', latest_date,
          'latestHolderCount', latest_holder_count,
          'latestValueUsd', latest_value_usd
        )
        order by latest_date desc, latest_holder_count desc, latest_value_usd desc, display_name asc
      )
      from token_rows
    ), '[]'::jsonb),
    'cells', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'date', a.date_key,
          'tokenId', a.token_id,
          'holderCount', a.holder_count,
          'balanceSum', a.balance_sum,
          'valueUsdSum', a.value_usd_sum,
          'holderCountDelta', case when a.previous_holder_count is null then null else a.holder_count - a.previous_holder_count end,
          'balanceDelta', case when a.previous_balance_sum is null then null else a.balance_sum - a.previous_balance_sum end,
          'valueUsdDelta', case when a.previous_value_usd_sum is null then null else a.value_usd_sum - a.previous_value_usd_sum end,
          'holders', a.holders
        )
        order by a.date_key asc
      )
      from aggregate_with_prev a
      join token_rows tr on tr.token_id = a.token_id
    ), '[]'::jsonb)
  )
  into payload;
  return coalesce(payload, jsonb_build_object('dates', '[]'::jsonb, 'tokens', '[]'::jsonb, 'cells', '[]'::jsonb));
end;
$$;

create or replace function public.get_onchain_wallet_matrix(
  wallet_id_arg uuid,
  end_date_arg text default null,
  chain_keys_arg text[] default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  payload jsonb;
begin
  if not exists (select 1 from public.onchain_visible_wallet_ids() where wallet_id = wallet_id_arg) then
    return jsonb_build_object('meta', null, 'dates', '[]'::jsonb, 'tokens', '[]'::jsonb, 'cells', '[]'::jsonb);
  end if;

  with available_dates as (
    select distinct d.date_key
    from public.onchain_daily_wallet_token_views d
    where d.wallet_id = wallet_id_arg
      and (chain_keys_arg is null or cardinality(chain_keys_arg) = 0 or d.chain_key = any(chain_keys_arg))
      and (end_date_arg is null or d.date_key <= end_date_arg)
    order by d.date_key desc
    limit 14
  ),
  dates as (
    select date_key from available_dates order by date_key asc
  ),
  rows as (
    select
      d.date_key,
      t.id as token_id,
      t.token_key,
      t.chain_key,
      t.chain_index,
      t.token_contract_address,
      t.symbol,
      coalesce(nullif(t.display_name, ''), nullif(t.symbol, ''), public.onchain_short_address(t.token_contract_address)) as display_name,
      d.balance,
      d.holding_value_usd,
      d.balance_delta,
      d.value_usd_delta,
      d.state
    from public.onchain_daily_wallet_token_views d
    join dates on dates.date_key = d.date_key
    join public.onchain_tokens t on t.id = d.token_id
    where d.wallet_id = wallet_id_arg
      and (chain_keys_arg is null or cardinality(chain_keys_arg) = 0 or d.chain_key = any(chain_keys_arg))
  ),
  token_rows as (
    select distinct on (token_id)
      token_id,
      token_key,
      chain_key,
      chain_index,
      token_contract_address,
      symbol,
      display_name
    from rows
    order by token_id, date_key desc
  )
  select jsonb_build_object(
    'meta', (
      select jsonb_build_object(
        'walletId', w.id,
        'address', w.address,
        'addressShort', public.onchain_short_address(w.address),
        'displayName', coalesce(nullif(n.note, ''), nullif(w.admin_label, ''), public.onchain_short_address(w.address)),
        'adminLabel', w.admin_label,
        'userNote', coalesce(n.note, ''),
        'enabledChains', coalesce((
          select jsonb_agg(jsonb_build_object('key', c.chain_key, 'chainIndex', c.chain_index) order by c.chain_key)
          from public.onchain_wallet_chains c
          where c.wallet_id = w.id and c.enabled
        ), '[]'::jsonb)
      )
      from public.onchain_wallets w
      left join public.onchain_user_wallet_notes n on n.wallet_id = w.id and n.user_id = auth.uid()
      where w.id = wallet_id_arg
    ),
    'dates', coalesce((select jsonb_agg(date_key order by date_key) from dates), '[]'::jsonb),
    'tokens', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'tokenId', token_id,
          'tokenKey', token_key,
          'chainKey', chain_key,
          'chainIndex', chain_index,
          'contractAddress', token_contract_address,
          'symbol', symbol,
          'displayName', display_name
        )
        order by display_name asc
      )
      from token_rows
    ), '[]'::jsonb),
    'cells', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'date', date_key,
          'tokenId', token_id,
          'balance', balance,
          'valueUsd', holding_value_usd,
          'balanceDelta', balance_delta,
          'valueUsdDelta', value_usd_delta,
          'state', state
        )
        order by date_key asc
      )
      from rows
    ), '[]'::jsonb)
  )
  into payload;
  return payload;
end;
$$;

create or replace function public.get_onchain_overview()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  payload jsonb;
begin
  with visible_wallets as (
    select wallet_id from public.onchain_visible_wallet_ids()
  ),
  latest_date as (
    select max(date_key) as value
    from public.onchain_daily_wallet_token_views d
    join visible_wallets vw on vw.wallet_id = d.wallet_id
  ),
  latest_token_rows as (
    select
      t.id as token_id,
      t.token_key,
      t.chain_key,
      t.chain_index,
      t.symbol,
      coalesce(nullif(t.display_name, ''), nullif(t.symbol, ''), public.onchain_short_address(t.token_contract_address)) as display_name,
      count(distinct d.wallet_id)::int as holder_count,
      sum(d.balance) as balance_sum,
      sum(d.holding_value_usd) as value_usd_sum
    from public.onchain_daily_wallet_token_views d
    join latest_date ld on ld.value = d.date_key
    join visible_wallets vw on vw.wallet_id = d.wallet_id
    join public.onchain_tokens t on t.id = d.token_id
    group by t.id
    order by count(distinct d.wallet_id) desc, sum(d.holding_value_usd) desc
    limit 10
  ),
  new_token_rows as (
    select
      t.id as token_id,
      t.token_key,
      t.chain_key,
      t.chain_index,
      t.symbol,
      coalesce(nullif(t.display_name, ''), nullif(t.symbol, ''), public.onchain_short_address(t.token_contract_address)) as display_name,
      count(distinct d.wallet_id)::int as new_wallet_count,
      sum(d.balance) as balance_sum,
      sum(d.holding_value_usd) as value_usd_sum
    from public.onchain_daily_wallet_token_views d
    join latest_date ld on ld.value = d.date_key
    join visible_wallets vw on vw.wallet_id = d.wallet_id
    join public.onchain_tokens t on t.id = d.token_id
    where d.state = 'new'
    group by t.id
    order by count(distinct d.wallet_id) desc, sum(d.holding_value_usd) desc
    limit 10
  ),
  increased_token_rows as (
    select
      t.id as token_id,
      t.token_key,
      t.chain_key,
      t.chain_index,
      t.symbol,
      coalesce(nullif(t.display_name, ''), nullif(t.symbol, ''), public.onchain_short_address(t.token_contract_address)) as display_name,
      count(*)::int as increased_wallet_count,
      sum(d.balance_delta) as balance_delta_sum,
      sum(d.value_usd_delta) as value_usd_delta_sum
    from public.onchain_daily_wallet_token_views d
    join latest_date ld on ld.value = d.date_key
    join visible_wallets vw on vw.wallet_id = d.wallet_id
    join public.onchain_tokens t on t.id = d.token_id
    where d.state = 'increased'
    group by t.id
    order by sum(d.balance_delta) desc nulls last, count(*) desc
    limit 10
  ),
  active_wallets as (
    select
      w.id,
      w.address,
      public.onchain_short_address(w.address) as address_short,
      coalesce(nullif(n.note, ''), nullif(w.admin_label, ''), public.onchain_short_address(w.address)) as display_name,
      count(d.token_id)::int as token_count,
      sum(d.holding_value_usd) as value_usd_sum
    from public.onchain_wallets w
    join visible_wallets vw on vw.wallet_id = w.id
    left join public.onchain_user_wallet_notes n on n.wallet_id = w.id and n.user_id = auth.uid()
    left join public.onchain_daily_wallet_token_views d on d.wallet_id = w.id and d.date_key = (select value from latest_date)
    group by w.id, n.note
    order by count(d.token_id) desc, sum(d.holding_value_usd) desc nulls last
    limit 10
  )
  select jsonb_build_object(
    'latestDate', (select value from latest_date),
    'walletCount', (select count(*) from visible_wallets),
    'tokenCount', (select count(distinct token_id) from public.onchain_daily_wallet_token_views d join visible_wallets vw on vw.wallet_id = d.wallet_id where d.date_key = (select value from latest_date)),
    'topTokens', coalesce((
      select jsonb_agg(to_jsonb(latest_token_rows) order by holder_count desc, value_usd_sum desc)
      from latest_token_rows
    ), '[]'::jsonb),
    'newTokens', coalesce((
      select jsonb_agg(to_jsonb(new_token_rows) order by new_wallet_count desc, value_usd_sum desc)
      from new_token_rows
    ), '[]'::jsonb),
    'increasedTokens', coalesce((
      select jsonb_agg(to_jsonb(increased_token_rows) order by balance_delta_sum desc nulls last, increased_wallet_count desc)
      from increased_token_rows
    ), '[]'::jsonb),
    'activeWallets', coalesce((
      select jsonb_agg(to_jsonb(active_wallets) order by token_count desc, value_usd_sum desc)
      from active_wallets
    ), '[]'::jsonb),
    'recentRuns', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'id', id,
          'kind', kind,
          'status', status,
          'summary', summary,
          'errorText', error_text,
          'createdAt', created_at,
          'startedAt', started_at,
          'finishedAt', finished_at
        )
        order by created_at desc
      )
      from (
        select *
        from public.onchain_fetch_runs
        where status <> 'pending' or public.is_current_user_admin()
        order by created_at desc
        limit 5
      ) runs
    ), '[]'::jsonb)
  )
  into payload;
  return payload;
end;
$$;

create or replace function public.list_onchain_admin_dashboard()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  payload jsonb;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin privileges required.';
  end if;

  select jsonb_build_object(
    'approvedCount', (select count(*) from public.onchain_wallets where status = 'approved'),
    'pendingCount', (select count(*) from public.onchain_wallet_requests where status = 'pending'),
    'wallets', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'id', w.id,
          'address', w.address,
          'addressShort', public.onchain_short_address(w.address),
          'adminLabel', w.admin_label,
          'status', w.status,
          'lastSnapshotAt', w.last_snapshot_at,
          'enabledChains', coalesce((
            select jsonb_agg(jsonb_build_object('key', c.chain_key, 'chainIndex', c.chain_index, 'enabled', c.enabled) order by c.chain_key)
            from public.onchain_wallet_chains c
            where c.wallet_id = w.id and c.enabled
          ), '[]'::jsonb)
        )
        order by coalesce(w.approved_at, w.updated_at, w.created_at) desc
      )
      from public.onchain_wallets w
      where w.status in ('approved', 'disabled')
    ), '[]'::jsonb),
    'requests', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'id', r.id,
          'rawInput', r.raw_input,
          'normalizedAddress', r.normalized_address,
          'status', r.status,
          'requesterEmail', coalesce(p.email::text, 'unknown'),
          'createdAt', r.created_at
        )
        order by r.created_at asc
      )
      from public.onchain_wallet_requests r
      left join public.profiles p on p.id = r.requester_id
      where r.status = 'pending'
    ), '[]'::jsonb),
    'runs', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'id', id,
          'kind', kind,
          'status', status,
          'summary', summary,
          'errorText', error_text,
          'createdAt', created_at,
          'startedAt', started_at,
          'finishedAt', finished_at
        )
        order by created_at desc
      )
      from (
        select *
        from public.onchain_fetch_runs
        order by created_at desc
        limit 20
      ) runs
    ), '[]'::jsonb)
  )
  into payload;
  return payload;
end;
$$;

insert into public.onchain_token_filter_rules (rule_type, symbol, note)
select 'stablecoin', symbol, 'default stablecoin filter'
from unnest(array['USDT','USDC','DAI','FDUSD','TUSD','USDE','SUSDE','USDS','PYUSD']) as symbol
on conflict do nothing;

insert into public.onchain_token_filter_rules (rule_type, symbol, note)
select 'core_asset', symbol, 'default core asset filter'
from unnest(array['ETH','WETH','STETH','WSTETH','WBTC','BTC','SOL','BNB','WBNB','CBETH','RETH']) as symbol
on conflict do nothing;

insert into public.onchain_wallets (address, address_kind, admin_label, status, approved_at)
values
  ('0xa7bfa56d1fbb7809b8424b452896707be408e1bc', 'evm', '恰米', 'approved', now()),
  ('0xa05ec35f7d1eba823cff2ed26aeaed419683742f', 'evm', '裤子', 'approved', now())
on conflict (address) do update set
  admin_label = excluded.admin_label,
  status = 'approved',
  approved_at = coalesce(public.onchain_wallets.approved_at, now()),
  updated_at = now();

insert into public.onchain_wallet_chains (wallet_id, chain_key, chain_index, enabled)
select w.id, chain_key, public.onchain_chain_index(chain_key), true
from public.onchain_wallets w
cross join lateral (
  values
    ('bsc')
) as chains(chain_key)
where w.address = '0xa7bfa56d1fbb7809b8424b452896707be408e1bc'
on conflict (wallet_id, chain_key) do update set enabled = true, chain_index = excluded.chain_index;

insert into public.onchain_wallet_chains (wallet_id, chain_key, chain_index, enabled)
select w.id, chain_key, public.onchain_chain_index(chain_key), true
from public.onchain_wallets w
cross join lateral (
  values
    ('bsc'),
    ('ethereum'),
    ('base')
) as chains(chain_key)
where w.address = '0xa05ec35f7d1eba823cff2ed26aeaed419683742f'
on conflict (wallet_id, chain_key) do update set enabled = true, chain_index = excluded.chain_index;

revoke all on function public.list_onchain_wallets(text, integer) from public;
revoke all on function public.submit_onchain_wallet(text, text[]) from public;
revoke all on function public.set_onchain_wallet_subscription(uuid, boolean) from public;
revoke all on function public.set_onchain_wallet_note(uuid, text) from public;
revoke all on function public.approve_onchain_wallet_request(uuid) from public;
revoke all on function public.reject_onchain_wallet_request(uuid) from public;
revoke all on function public.admin_update_onchain_wallet(uuid, text, text[], text) from public;
revoke all on function public.enqueue_onchain_fetch() from public;
revoke all on function public.list_my_onchain_wallet_requests() from public;
revoke all on function public.get_onchain_token_matrix(text, text[]) from public;
revoke all on function public.get_onchain_wallet_matrix(uuid, text, text[]) from public;
revoke all on function public.get_onchain_overview() from public;
revoke all on function public.list_onchain_admin_dashboard() from public;

grant execute on function public.list_onchain_wallets(text, integer) to anon, authenticated;
grant execute on function public.submit_onchain_wallet(text, text[]) to authenticated;
grant execute on function public.set_onchain_wallet_subscription(uuid, boolean) to authenticated;
grant execute on function public.set_onchain_wallet_note(uuid, text) to authenticated;
grant execute on function public.approve_onchain_wallet_request(uuid) to authenticated;
grant execute on function public.reject_onchain_wallet_request(uuid) to authenticated;
grant execute on function public.admin_update_onchain_wallet(uuid, text, text[], text) to authenticated;
grant execute on function public.enqueue_onchain_fetch() to authenticated;
grant execute on function public.list_my_onchain_wallet_requests() to authenticated;
grant execute on function public.get_onchain_token_matrix(text, text[]) to anon, authenticated;
grant execute on function public.get_onchain_wallet_matrix(uuid, text, text[]) to anon, authenticated;
grant execute on function public.get_onchain_overview() to anon, authenticated;
grant execute on function public.list_onchain_admin_dashboard() to authenticated;
