create or replace function public.get_home_feed_preview(
  limit_arg integer default 6,
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
  current_is_admin boolean := public.is_current_user_admin();
  safe_limit integer;
  safe_domain text := case when domain_arg = 'crypto' then 'crypto' else 'stock' end;
  rows_payload jsonb := '[]'::jsonb;
begin
  safe_limit := case
    when current_uid is null then least(greatest(coalesce(limit_arg, 3), 1), 3)
    else least(greatest(coalesce(limit_arg, 6), 1), 24)
  end;

  with visible_accounts as (
    select
      a.id,
      a.username,
      a.display_name,
      a.profile_url
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
      va.id as account_id,
      va.username,
      va.display_name,
      va.profile_url,
      ads.date_key,
      ads.status,
      ads.note_count_today,
      ads.summary_text,
      ads.updated_at,
      (
        select count(*)
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
      )::integer as viewpoint_count
    from visible_accounts va
    join public.author_daily_summaries ads on ads.account_id = va.id
    where ads.analysis_domain = safe_domain
  ),
  ranked_days as (
    select *
    from eligible_days
    where viewpoint_count > 0
    order by date_key desc, updated_at desc, username asc
    limit safe_limit
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'id', ranked_days.account_id::text || '-' || ranked_days.date_key,
        'username', ranked_days.username,
        'display_name', coalesce(nullif(ranked_days.display_name, ''), ranked_days.username),
        'profile_url', ranked_days.profile_url,
        'date', ranked_days.date_key,
        'status', ranked_days.status,
        'note_count', ranked_days.note_count_today,
        'summary', case when safe_domain = 'crypto' then '' else ranked_days.summary_text end,
        'viewpoint_count', ranked_days.viewpoint_count,
        'updated_at', ranked_days.updated_at
      )
      order by ranked_days.date_key desc, ranked_days.updated_at desc, ranked_days.username asc
    ),
    '[]'::jsonb
  )
  into rows_payload
  from ranked_days;

  return jsonb_build_object(
    'rows', rows_payload
  );
end;
$$;

revoke all on function public.get_home_feed_preview(integer, text) from public;
grant execute on function public.get_home_feed_preview(integer, text) to anon, authenticated;
