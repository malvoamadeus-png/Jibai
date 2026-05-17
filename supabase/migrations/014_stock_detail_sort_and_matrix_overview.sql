-- Restore full stock detail history, add server-side stock sorting, and expose
-- a seven-day stock x author opinion matrix for the public web app.

create or replace function public.list_visible_entities(
  entity_type_arg text,
  query_arg text default '',
  limit_arg integer default 100
)
returns table (
  entity_key text,
  display_name text,
  ticker text,
  market text,
  latest_date text,
  mention_days integer,
  total_mentions integer,
  updated_at timestamptz
)
language plpgsql
security definer
stable
set search_path = public
as $$
begin
  return query
  select *
  from public.list_visible_entities(entity_type_arg, query_arg, limit_arg, 'date_desc');
end;
$$;

create or replace function public.list_visible_entities(
  entity_type_arg text,
  query_arg text,
  limit_arg integer,
  sort_arg text
)
returns table (
  entity_key text,
  display_name text,
  ticker text,
  market text,
  latest_date text,
  mention_days integer,
  total_mentions integer,
  updated_at timestamptz
)
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  safe_limit integer;
  safe_sort text;
begin
  safe_limit := case
    when current_uid is null then 1
    else least(greatest(coalesce(limit_arg, 100), 1), 500)
  end;
  safe_sort := case
    when coalesce(sort_arg, '') in ('date_desc', 'date_asc', 'count_desc', 'count_asc') then sort_arg
    else 'date_desc'
  end;

  if entity_type_arg <> 'stock' then
    return;
  end if;

  return query
  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and xa.status = 'approved'
  ),
  expanded as (
    select
      se.security_key::text as key_value,
      se.display_name::text as display_value,
      se.ticker::text as ticker_value,
      se.market::text as market_value,
      sdv.date_key::text as date_value,
      sdv.updated_at,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
      and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
      and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
  )
  select
    e.key_value,
    e.display_value,
    e.ticker_value,
    e.market_value,
    max(e.date_value)::text,
    count(distinct e.date_value)::integer,
    count(*)::integer,
    max(e.updated_at)
  from expanded e
  where e.author_name <> ''
    and (
      current_uid is null
      or current_is_admin
      or e.author_name in (select va.author_name from visible_authors va)
    )
    and (
      current_uid is null
      or coalesce(trim(query_arg), '') = ''
      or lower(e.key_value) like '%' || lower(trim(query_arg)) || '%'
      or lower(e.display_value) like '%' || lower(trim(query_arg)) || '%'
      or lower(coalesce(e.ticker_value, '')) like '%' || lower(trim(query_arg)) || '%'
    )
  group by e.key_value, e.display_value, e.ticker_value, e.market_value
  order by
    case when safe_sort = 'date_desc' then max(e.date_value) end desc nulls last,
    case when safe_sort = 'date_asc' then max(e.date_value) end asc nulls last,
    case when safe_sort = 'count_desc' then count(*) end desc nulls last,
    case when safe_sort = 'count_asc' then count(*) end asc nulls last,
    e.display_value asc
  limit safe_limit;
end;
$$;

create or replace function public.get_visible_entity_timeline(
  entity_type_arg text,
  entity_key_arg text,
  page_arg integer default 1,
  page_size_arg integer default 20
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
  safe_page integer := greatest(coalesce(page_arg, 1), 1);
  safe_page_size integer;
  offset_value integer;
  preview_key text;
  total_count integer := 0;
  security_id_value uuid;
  meta_payload jsonb;
  rows_payload jsonb;
  markers_payload jsonb := '[]'::jsonb;
  candles_payload jsonb := '[]'::jsonb;
  chart_payload jsonb;
  latest_source text;
begin
  if entity_type_arg <> 'stock' then
    return null;
  end if;

  safe_page_size := case
    when current_uid is null then least(greatest(coalesce(page_size_arg, 3), 1), 3)
    else least(greatest(coalesce(page_size_arg, 20), 1), 100)
  end;
  offset_value := (safe_page - 1) * safe_page_size;

  select preview.key_value
  into preview_key
  from (
    select
      se.security_key::text as key_value,
      max(sdv.date_key) as latest_date,
      count(*) as total_mentions
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) as view_item(value)
    where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
      and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
      and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
      and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
    group by se.security_key
    order by max(sdv.date_key) desc, count(*) desc
    limit 1
  ) preview;

  if current_uid is null and coalesce(entity_key_arg, '') <> coalesce(preview_key, '') then
    return null;
  end if;

  select
    se.id,
    jsonb_build_object(
      'key', se.security_key,
      'display_name', se.display_name,
      'ticker', se.ticker,
      'market', se.market
    )
  into security_id_value, meta_payload
  from public.security_entities se
  where se.security_key = entity_key_arg
  limit 1;

  if meta_payload is null then
    return null;
  end if;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and xa.status = 'approved'
  ),
  raw_days as (
    select
      sdv.date_key,
      sdv.updated_at,
      (
        select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
        from jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
        where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
          and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
          and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
          and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
          and (
            current_uid is null
            or current_is_admin
            or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
              select va.author_name from visible_authors va
            )
          )
      ) as author_views
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    where se.security_key = entity_key_arg
  ),
  visible_days as (
    select *
    from raw_days
    where jsonb_array_length(author_views) > 0
  )
  select
    count(*)::integer,
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'date', date_key,
          'mention_count', jsonb_array_length(author_views),
          'author_views', author_views
        )
        order by date_key asc
      ),
      '[]'::jsonb
    )
  into total_count, markers_payload
  from visible_days;

  if total_count = 0 then
    return null;
  end if;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and xa.status = 'approved'
  ),
  raw_days as (
    select
      sdv.date_key,
      sdv.updated_at,
      (
        select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
        from jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
        where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
          and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
          and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
          and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
          and (
            current_uid is null
            or current_is_admin
            or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
              select va.author_name from visible_authors va
            )
          )
      ) as author_views
    from public.security_daily_views sdv
    join public.security_entities se on se.id = sdv.security_id
    where se.security_key = entity_key_arg
  ),
  visible_days as (
    select *
    from raw_days
    where jsonb_array_length(author_views) > 0
    order by date_key desc
    limit safe_page_size offset offset_value
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'date', date_key,
        'mention_count', jsonb_array_length(author_views),
        'author_views', author_views,
        'updated_at', updated_at
      )
      order by date_key desc
    ),
    '[]'::jsonb
  )
  into rows_payload
  from visible_days;

  if current_uid is null then
    chart_payload := jsonb_build_object(
      'sourceLabel', null,
      'message', 'Sign in to view market data.',
      'candles', '[]'::jsonb,
      'markers', '[]'::jsonb
    );
  else
    select coalesce(
      jsonb_agg(
        jsonb_build_object(
          'date', date_key,
          'open', open_price,
          'high', high_price,
          'low', low_price,
          'close', close_price,
          'volume', volume
        )
        order by date_key asc
      ),
      '[]'::jsonb
    )
    into candles_payload
    from public.security_daily_prices
    where security_id = security_id_value
      and date_key >= (current_date - interval '180 days')::date::text;

    select source
    into latest_source
    from public.security_daily_prices
    where security_id = security_id_value
    order by date_key desc
    limit 1;

    chart_payload := jsonb_build_object(
      'sourceLabel', latest_source,
      'message', case
        when jsonb_array_length(candles_payload) > 0 then null
        else 'Market data is temporarily unavailable; the viewpoint timeline is still shown.'
      end,
      'candles', candles_payload,
      'markers', markers_payload
    );
  end if;

  return jsonb_build_object(
    'meta', meta_payload,
    'timeline', jsonb_build_object(
      'rows', rows_payload,
      'total', total_count,
      'page', safe_page,
      'page_size', safe_page_size,
      'total_pages', greatest(1, ceil(total_count::numeric / safe_page_size)::integer)
    ),
    'chart', chart_payload
  );
end;
$$;

create or replace function public.get_visible_stock_matrix(
  end_date_arg text default null
)
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  requested_end date;
  latest_visible_date date;
  effective_end date;
  effective_start date;
  previous_end date;
  next_end date;
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
    where s.user_id = current_uid
      and xa.status = 'approved'
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
      or e.author_name in (select va.author_name from visible_authors va)
    );

  if latest_visible_date is null then
    return jsonb_build_object(
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
  effective_start := effective_end - 6;
  previous_end := effective_start - 1;
  next_end := case
    when effective_end < latest_visible_date then least(effective_end + 7, latest_visible_date)
    else null
  end;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and xa.status = 'approved'
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
    where s.user_id = current_uid
      and xa.status = 'approved'
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
    where s.user_id = current_uid
      and xa.status = 'approved'
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

revoke all on function public.list_visible_entities(text, text, integer) from public;
revoke all on function public.list_visible_entities(text, text, integer, text) from public;
revoke all on function public.get_visible_entity_timeline(text, text, integer, integer) from public;
revoke all on function public.get_visible_stock_matrix(text) from public;

grant execute on function public.list_visible_entities(text, text, integer) to anon, authenticated;
grant execute on function public.list_visible_entities(text, text, integer, text) to anon, authenticated;
grant execute on function public.get_visible_entity_timeline(text, text, integer, integer) to anon, authenticated;
grant execute on function public.get_visible_stock_matrix(text) to anon, authenticated;
