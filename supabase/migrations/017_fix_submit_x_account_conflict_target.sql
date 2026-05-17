-- Avoid PL/pgSQL ambiguity in submit_x_account caused by an ON CONFLICT
-- target using account_id while the function also returns account_id.

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
  normalized_username_value citext;
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
begin
  if auth.uid() is null then
    raise exception 'Authentication required.';
  end if;

  normalized_username_value := lower(trim(username_arg))::citext;
  if normalized_username_value::text !~ '^[a-z0-9_]{1,15}$' then
    raise exception 'Invalid X username.';
  end if;

  select xa.id
  into account_id_value
  from public.x_accounts xa
  where xa.username = normalized_username_value;

  if account_id_value is null then
    insert into public.x_accounts (username, display_name, profile_url, status, submitted_by)
    values (
      normalized_username_value,
      normalized_username_value::text,
      'https://x.com/' || normalized_username_value::text,
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

  select ar.id
  into request_id_value
  from public.account_requests ar
  where ar.account_id = account_id_value
    and ar.domain = safe_domain
    and ar.requester_id = auth.uid();

  if request_id_value is null then
    begin
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
        normalized_username_value,
        safe_domain,
        request_status_value,
        case when request_status_value = 'approved' then now() else null end
      )
      returning id into request_id_value;
    exception when unique_violation then
      update public.account_requests ar
      set
        raw_input = raw_input_arg,
        normalized_username = normalized_username_value,
        status = request_status_value,
        reviewed_at = case when request_status_value = 'approved' then now() else null end,
        updated_at = now()
      where ar.account_id = account_id_value
        and ar.domain = safe_domain
        and ar.requester_id = auth.uid()
      returning ar.id into request_id_value;
    end;
  else
    update public.account_requests ar
    set
      raw_input = raw_input_arg,
      normalized_username = normalized_username_value,
      status = request_status_value,
      reviewed_at = case when request_status_value = 'approved' then now() else null end,
      updated_at = now()
    where ar.id = request_id_value
    returning ar.id into request_id_value;
  end if;

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
