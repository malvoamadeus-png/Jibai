alter table public.security_mentions
  add column if not exists signal_type text not null default 'unknown';

alter table public.content_viewpoints
  add column if not exists signal_type text not null default 'unknown';

delete from public.author_daily_summaries;
delete from public.security_daily_views;
delete from public.theme_daily_views;
delete from public.security_mentions;
delete from public.content_viewpoints;
delete from public.content_analyses;

create or replace function public.list_visible_authors(
  query_arg text default '',
  limit_arg integer default 100
)
returns table (
  account_id uuid,
  platform text,
  account_name text,
  author_nickname text,
  profile_url text,
  latest_date text,
  latest_status text,
  total_days integer,
  total_notes integer,
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
begin
  safe_limit := case
    when current_uid is null then 1
    else least(greatest(coalesce(limit_arg, 100), 1), 500)
  end;

  return query
  with visible_accounts as (
    select a.*
    from public.x_accounts a
    where a.status = 'approved'
      and (
        current_uid is null
        or current_is_admin
        or exists (
          select 1
          from public.user_subscriptions s
          where s.user_id = current_uid
            and s.account_id = a.id
        )
      )
  ),
  eligible_days as (
    select
      va.id,
      va.username,
      va.display_name,
      va.profile_url,
      ads.date_key,
      ads.status,
      ads.note_count_today,
      ads.updated_at
    from visible_accounts va
    join public.author_daily_summaries ads on ads.account_id = va.id
    where ads.date_key >= ((now() at time zone 'Asia/Shanghai')::date - 2)::text
      and exists (
      select 1
      from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) as viewpoint(value)
      where coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
        and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
        and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
        and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
    )
  )
  select
    d.id as account_id,
    'x'::text as platform,
    d.username::text as account_name,
    coalesce(nullif(d.display_name, ''), d.username::text)::text as author_nickname,
    d.profile_url::text,
    max(d.date_key)::text as latest_date,
    (array_agg(d.status order by d.date_key desc))[1]::text as latest_status,
    count(*)::integer as total_days,
    coalesce(sum(d.note_count_today), 0)::integer as total_notes,
    max(d.updated_at) as updated_at
  from eligible_days d
  where (
    current_uid is null
    or coalesce(trim(query_arg), '') = ''
    or lower(d.username::text) like '%' || lower(trim(query_arg)) || '%'
    or lower(coalesce(d.display_name, '')) like '%' || lower(trim(query_arg)) || '%'
  )
  group by d.id, d.username, d.display_name, d.profile_url
  order by max(d.date_key) desc, max(d.updated_at) desc, d.username::text asc
  limit safe_limit;
end;
$$;

create or replace function public.get_visible_author_timeline(
  account_id_arg uuid,
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
  preview_account_id uuid;
  can_view boolean := false;
  total_count integer := 0;
  meta_payload jsonb;
  rows_payload jsonb;
begin
  safe_page_size := case
    when current_uid is null then least(greatest(coalesce(page_size_arg, 3), 1), 3)
    else least(greatest(coalesce(page_size_arg, 20), 1), 100)
  end;
  offset_value := (safe_page - 1) * safe_page_size;

  select ranked.account_id
  into preview_account_id
  from (
    select
      a.id as account_id,
      max(ads.date_key) as latest_date,
      max(ads.updated_at) as latest_updated_at
    from public.x_accounts a
    join public.author_daily_summaries ads on ads.account_id = a.id
    where a.status = 'approved'
      and ads.date_key >= ((now() at time zone 'Asia/Shanghai')::date - 2)::text
      and exists (
        select 1
        from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) as viewpoint(value)
        where coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
          and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
          and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
          and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
      )
    group by a.id
    order by max(ads.date_key) desc, max(ads.updated_at) desc
    limit 1
  ) ranked;

  select exists (
    select 1
    from public.x_accounts a
    where a.id = account_id_arg
      and a.status = 'approved'
      and (
        current_is_admin
        or (current_uid is not null and exists (
          select 1
          from public.user_subscriptions s
          where s.user_id = current_uid
            and s.account_id = a.id
        ))
        or (current_uid is null and a.id = preview_account_id)
      )
  )
  into can_view;

  if not can_view then
    return null;
  end if;

  select count(*)::integer
  into total_count
  from public.author_daily_summaries ads
  where ads.account_id = account_id_arg
    and ads.date_key >= ((now() at time zone 'Asia/Shanghai')::date - 2)::text
    and exists (
      select 1
      from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) as viewpoint(value)
      where coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
        and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
        and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
        and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
    );

  if total_count = 0 then
    return null;
  end if;

  select jsonb_build_object(
    'account_id', a.id,
    'platform', 'x',
    'account_name', a.username::text,
    'author_nickname', coalesce(nullif(a.display_name, ''), a.username::text),
    'author_id', coalesce(a.x_user_id, ''),
    'profile_url', a.profile_url
  )
  into meta_payload
  from public.x_accounts a
  where a.id = account_id_arg
  limit 1;

  select coalesce(jsonb_agg(day_payload order by date_key desc), '[]'::jsonb)
  into rows_payload
  from (
    select
      ads.date_key,
      jsonb_build_object(
        'date', ads.date_key,
        'status', ads.status,
        'note_count_today', ads.note_count_today,
        'summary_text', ads.summary_text,
        'note_ids', coalesce(ads.note_ids_json, '[]'::jsonb),
        'notes', coalesce(ads.notes_json, '[]'::jsonb),
        'viewpoints', (
          select coalesce(jsonb_agg(viewpoint.value order by viewpoint.ordinality), '[]'::jsonb)
          from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) with ordinality as viewpoint(value, ordinality)
          where coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
            and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
            and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
            and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
        ),
        'mentioned_stocks', coalesce(ads.mentioned_stocks_json, '[]'::jsonb),
        'mentioned_themes', '[]'::jsonb,
        'updated_at', ads.updated_at
      ) as day_payload
    from public.author_daily_summaries ads
    where ads.account_id = account_id_arg
      and ads.date_key >= ((now() at time zone 'Asia/Shanghai')::date - 2)::text
      and exists (
        select 1
        from jsonb_array_elements(coalesce(ads.viewpoints_json, '[]'::jsonb)) as viewpoint(value)
        where coalesce(viewpoint.value ->> 'entity_type', '') = 'stock'
          and coalesce(viewpoint.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
          and coalesce(viewpoint.value ->> 'direction', '') in ('positive', 'negative')
          and coalesce(viewpoint.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
      )
    order by ads.date_key desc
    limit safe_page_size offset offset_value
  ) page_rows;

  return jsonb_build_object(
    'meta', meta_payload,
    'timeline', jsonb_build_object(
      'rows', rows_payload,
      'total', total_count,
      'page', safe_page,
      'page_size', safe_page_size,
      'total_pages', greatest(1, ceil(total_count::numeric / safe_page_size)::integer)
    )
  );
end;
$$;

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
declare
  current_uid uuid := auth.uid();
  current_is_admin boolean := public.is_current_user_admin();
  safe_limit integer;
begin
  safe_limit := case
    when current_uid is null then 1
    else least(greatest(coalesce(limit_arg, 100), 1), 500)
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
    where sdv.date_key >= ((now() at time zone 'Asia/Shanghai')::date - 2)::text
      and coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
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
  order by max(e.date_value) desc, count(*) desc, e.display_value asc
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
    where sdv.date_key >= ((now() at time zone 'Asia/Shanghai')::date - 2)::text
      and coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
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
      and sdv.date_key >= ((now() at time zone 'Asia/Shanghai')::date - 2)::text
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
      and sdv.date_key >= ((now() at time zone 'Asia/Shanghai')::date - 2)::text
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

revoke all on function public.list_visible_authors(text, integer) from public;
revoke all on function public.get_visible_author_timeline(uuid, integer, integer) from public;
revoke all on function public.list_visible_entities(text, text, integer) from public;
revoke all on function public.get_visible_entity_timeline(text, text, integer, integer) from public;

grant execute on function public.list_visible_authors(text, integer) to anon, authenticated;
grant execute on function public.get_visible_author_timeline(uuid, integer, integer) to anon, authenticated;
grant execute on function public.list_visible_entities(text, text, integer) to anon, authenticated;
grant execute on function public.get_visible_entity_timeline(text, text, integer, integer) to anon, authenticated;
