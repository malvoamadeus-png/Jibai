create or replace function public.submit_x_account(raw_input_arg text, username_arg text)
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
begin
  if auth.uid() is null then
    raise exception 'Authentication required.';
  end if;

  normalized_username := lower(trim(username_arg))::citext;
  if normalized_username::text !~ '^[a-z0-9_]{1,15}$' then
    raise exception 'Invalid X username.';
  end if;

  select id, status
  into account_id_value, account_status_value
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
    returning id, status into account_id_value, account_status_value;
  end if;

  request_status_value := case when account_status_value = 'approved' then 'approved' else 'pending' end;

  insert into public.account_requests (
    account_id,
    requester_id,
    raw_input,
    normalized_username,
    status,
    reviewed_at
  )
  values (
    account_id_value,
    auth.uid(),
    raw_input_arg,
    normalized_username,
    request_status_value,
    case when request_status_value = 'approved' then now() else null end
  )
  on conflict on constraint account_requests_account_id_requester_id_key do update
  set
    raw_input = excluded.raw_input,
    normalized_username = excluded.normalized_username,
    status = excluded.status,
    reviewed_at = excluded.reviewed_at,
    updated_at = now()
  returning id into request_id_value;

  if account_status_value = 'approved' then
    insert into public.user_subscriptions (user_id, account_id)
    values (auth.uid(), account_id_value)
    on conflict do nothing;
  end if;

  return query select account_id_value, request_id_value, account_status_value, request_status_value;
end;
$$;

grant execute on function public.submit_x_account(text, text) to authenticated;
