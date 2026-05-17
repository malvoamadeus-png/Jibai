-- Fix submit_x_account after adding domain-aware account fields.
-- The function returns a column named account_id; qualify table columns inside
-- PL/pgSQL so Postgres does not confuse output variables with table columns.

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

  select xa.id
  into account_id_value
  from public.x_accounts xa
  where xa.username = normalized_username;

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
  on conflict on constraint account_domains_pkey do nothing;

  select ad.status
  into account_status_value
  from public.account_domains ad
  where ad.account_id = account_id_value
    and ad.domain = safe_domain;

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
    on conflict on constraint user_subscriptions_pkey do nothing;
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
