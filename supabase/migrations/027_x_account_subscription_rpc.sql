create or replace function public.set_x_account_subscription(
  account_id_arg uuid,
  subscribed_arg boolean,
  domain_arg text default 'stock'
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
begin
  if current_uid is null then
    raise exception 'Authentication required.';
  end if;

  if subscribed_arg then
    if not exists (
      select 1
      from public.account_domains ad
      where ad.account_id = account_id_arg
        and ad.domain = safe_domain
        and ad.status = 'approved'
    ) then
      raise exception 'Account is not approved for this domain.';
    end if;

    insert into public.user_subscriptions (user_id, account_id, domain)
    values (current_uid, account_id_arg, safe_domain)
    on conflict on constraint user_subscriptions_pkey do nothing;
  else
    delete from public.user_subscriptions
    where user_id = current_uid
      and account_id = account_id_arg
      and domain = safe_domain;
  end if;
end;
$$;

revoke all on function public.set_x_account_subscription(uuid, boolean, text) from public;
grant execute on function public.set_x_account_subscription(uuid, boolean, text) to authenticated;
