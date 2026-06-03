create table if not exists public.domain_runtime_controls (
  domain text primary key check (domain in ('stock', 'crypto')),
  pipeline_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  updated_by uuid references auth.users(id) on delete set null
);

drop trigger if exists set_domain_runtime_controls_updated_at on public.domain_runtime_controls;
create trigger set_domain_runtime_controls_updated_at before update on public.domain_runtime_controls
for each row execute function public.set_updated_at();

revoke all on table public.domain_runtime_controls from public;

insert into public.domain_runtime_controls (domain, pipeline_enabled)
values
  ('stock', true),
  ('crypto', true)
on conflict (domain) do nothing;

create or replace function public.is_domain_pipeline_enabled(domain_arg text default 'stock')
returns boolean
language sql
stable
set search_path = public
as $$
  select coalesce(
    (
      select control.pipeline_enabled
      from public.domain_runtime_controls control
      where control.domain = case when domain_arg = 'crypto' then 'crypto' else 'stock' end
      limit 1
    ),
    true
  );
$$;

create or replace function public.set_domain_pipeline_enabled(
  domain_arg text,
  enabled_arg boolean
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
  current_uid uuid := auth.uid();
  row_value public.domain_runtime_controls%rowtype;
begin
  if not public.is_current_user_admin() then
    raise exception 'admin only';
  end if;

  insert into public.domain_runtime_controls(domain, pipeline_enabled, updated_by)
  values (safe_domain, coalesce(enabled_arg, true), current_uid)
  on conflict (domain) do update
  set
    pipeline_enabled = excluded.pipeline_enabled,
    updated_by = excluded.updated_by,
    updated_at = now()
  returning * into row_value;

  return jsonb_build_object(
    'domain', row_value.domain,
    'pipeline_enabled', row_value.pipeline_enabled,
    'updated_at', row_value.updated_at
  );
end;
$$;

create or replace function public.list_crypto_admin_controls()
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_is_admin boolean := public.is_current_user_admin();
begin
  if not current_is_admin then
    raise exception 'admin only';
  end if;

  return jsonb_build_object(
    'runtime_control',
    (
      select jsonb_build_object(
        'domain', control.domain,
        'pipeline_enabled', control.pipeline_enabled,
        'updated_at', control.updated_at
      )
      from public.domain_runtime_controls control
      where control.domain = 'crypto'
      limit 1
    ),
    'blocked_terms',
    coalesce(
      (
        select jsonb_agg(
          jsonb_build_object(
            'term', term,
            'created_at', created_at,
            'updated_at', updated_at
          )
          order by term asc
        )
        from public.crypto_asset_blocklist
      ),
      '[]'::jsonb
    ),
    'deleted_assets',
    coalesce(
      (
        select jsonb_agg(
          jsonb_build_object(
            'asset_key', d.asset_key,
            'display_name', coalesce(ce.display_name, d.asset_key),
            'reason', d.reason,
            'created_at', d.created_at,
            'updated_at', d.updated_at
          )
          order by d.updated_at desc, d.asset_key asc
        )
        from public.crypto_asset_admin_deletions d
        left join public.crypto_entities ce on ce.asset_key = d.asset_key
      ),
      '[]'::jsonb
    )
  );
end;
$$;

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

  if request_domain = 'crypto' and not public.is_domain_pipeline_enabled(request_domain) then
    raise exception 'Crypto pipeline is disabled.';
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

  if safe_domain = 'crypto' and not public.is_domain_pipeline_enabled(safe_domain) then
    raise exception 'Crypto pipeline is disabled.';
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

revoke all on function public.is_domain_pipeline_enabled(text) from public;
revoke all on function public.set_domain_pipeline_enabled(text, boolean) from public;
revoke all on function public.list_crypto_admin_controls() from public;

grant execute on function public.is_domain_pipeline_enabled(text) to anon, authenticated;
grant execute on function public.set_domain_pipeline_enabled(text, boolean) to authenticated;
grant execute on function public.list_crypto_admin_controls() to authenticated;
grant execute on function public.approve_account_request(uuid) to authenticated;
grant execute on function public.enqueue_manual_crawl(text) to authenticated;
