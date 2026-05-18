create or replace function public.get_visible_stock_matrix(
  end_date_arg text,
  granularity_arg text
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
  safe_granularity text := case when coalesce(granularity_arg, '') = 'day' then 'day' else 'week' end;
  window_days integer := case when coalesce(granularity_arg, '') = 'day' then 0 else 6 end;
  step_days integer := case when coalesce(granularity_arg, '') = 'day' then 1 else 7 end;
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
      'granularity', safe_granularity,
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
  effective_start := effective_end - window_days;
  previous_end := effective_end - step_days;
  next_end := case
    when effective_end < latest_visible_date then least(effective_end + step_days, latest_visible_date)
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
    'granularity', safe_granularity,
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

create or replace function public.get_visible_stock_matrix(
  end_date_arg text default null
)
returns jsonb
language sql
security definer
stable
set search_path = public
as $$
  select public.get_visible_stock_matrix(end_date_arg, 'week');
$$;

revoke all on function public.get_visible_stock_matrix(text, text) from public;
revoke all on function public.get_visible_stock_matrix(text) from public;

grant execute on function public.get_visible_stock_matrix(text, text) to anon, authenticated;
grant execute on function public.get_visible_stock_matrix(text) to anon, authenticated;
