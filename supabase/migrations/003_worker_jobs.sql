-- Alibaba Cloud worker job orchestration for the public app.
-- Run this after 002_direct_client_mode.sql.

drop policy if exists "crawl jobs admin read" on public.crawl_jobs;
create policy "crawl jobs admin read" on public.crawl_jobs
for select to authenticated using (public.is_current_user_admin());

drop policy if exists "crawl runs admin read" on public.crawl_runs;
create policy "crawl runs admin read" on public.crawl_runs
for select to authenticated using (public.is_current_user_admin());

drop policy if exists "crawl account runs admin read" on public.crawl_account_runs;
create policy "crawl account runs admin read" on public.crawl_account_runs
for select to authenticated using (public.is_current_user_admin());

create or replace function public.approve_account_request(request_id_arg uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  account_id_value uuid;
  existing_status text;
  approved_count integer;
  backfill_completed_at_value timestamptz;
  should_enqueue_backfill boolean;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin access required.';
  end if;

  select account_id
  into account_id_value
  from public.account_requests
  where id = request_id_arg;

  if account_id_value is null then
    raise exception 'Request not found.';
  end if;

  select status, backfill_completed_at
  into existing_status, backfill_completed_at_value
  from public.x_accounts
  where id = account_id_value;

  if existing_status is distinct from 'approved' then
    select count(*) into approved_count
    from public.x_accounts
    where status = 'approved';

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
    approved_at = now(),
    rejected_at = null,
    disabled_at = null
  where id = account_id_value;

  update public.account_requests
  set
    status = 'approved',
    reviewed_by = auth.uid(),
    reviewed_at = now()
  where account_id = account_id_value
    and status = 'pending';

  insert into public.user_subscriptions (user_id, account_id)
  select requester_id, account_id_value
  from public.account_requests
  where account_id = account_id_value
    and status = 'approved'
  on conflict do nothing;

  if should_enqueue_backfill then
    insert into public.crawl_jobs (
      kind,
      status,
      account_id,
      requested_by,
      dedupe_key,
      metadata_json
    )
    values (
      'initial_backfill',
      'pending',
      account_id_value,
      auth.uid(),
      'initial_backfill:' || account_id_value::text,
      jsonb_build_object(
        'source', 'approve',
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

create or replace function public.enqueue_manual_crawl()
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  job_id_value uuid;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin access required.';
  end if;

  insert into public.crawl_jobs (
    kind,
    status,
    requested_by,
    metadata_json
  )
  values (
    'manual_crawl',
    'pending',
    auth.uid(),
    jsonb_build_object('source', 'admin-ui')
  )
  returning id into job_id_value;

  return job_id_value;
end;
$$;

grant execute on function public.enqueue_manual_crawl() to authenticated;
