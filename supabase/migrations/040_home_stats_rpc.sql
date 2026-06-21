create or replace function public.get_home_stats(
  domain_arg text default 'stock'
)
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
  approved_count integer := 0;
  subscribed_count integer := 0;
begin
  select count(*)::integer
  into approved_count
  from public.account_domains ad
  where ad.domain = safe_domain
    and ad.status = 'approved';

  if current_uid is not null then
    select count(*)::integer
    into subscribed_count
    from public.user_subscriptions s
    join public.account_domains ad
      on ad.account_id = s.account_id
     and ad.domain = s.domain
    where s.user_id = current_uid
      and s.domain = safe_domain
      and ad.status = 'approved';
  end if;

  return jsonb_build_object(
    'approved_count', approved_count,
    'subscribed_count', subscribed_count
  );
end;
$$;

revoke all on function public.get_home_stats(text) from public;
grant execute on function public.get_home_stats(text) to anon, authenticated;
