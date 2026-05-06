create table if not exists public.security_daily_prices (
  id uuid primary key default gen_random_uuid(),
  security_id uuid not null references public.security_entities(id) on delete cascade,
  date_key text not null,
  open_price double precision not null,
  high_price double precision not null,
  low_price double precision not null,
  close_price double precision not null,
  volume double precision,
  source text not null,
  source_symbol text not null default '',
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(security_id, date_key)
);

create index if not exists idx_security_daily_prices_security_date
  on public.security_daily_prices(security_id, date_key desc);

alter table public.security_daily_prices enable row level security;

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
  safe_page_size := case
    when current_uid is null then least(greatest(coalesce(page_size_arg, 3), 1), 3)
    else least(greatest(coalesce(page_size_arg, 20), 1), 100)
  end;
  offset_value := (safe_page - 1) * safe_page_size;

  if entity_type_arg = 'stock' then
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
      where coalesce(view_item.value ->> 'stance', '') <> 'mention_only'
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
          where coalesce(view_item.value ->> 'stance', '') <> 'mention_only'
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
          where coalesce(view_item.value ->> 'stance', '') <> 'mention_only'
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
  end if;

  if entity_type_arg = 'theme' then
    select preview.key_value
    into preview_key
    from (
      select
        te.theme_key::text as key_value,
        max(tdv.date_key) as latest_date,
        count(*) as total_mentions
      from public.theme_daily_views tdv
      join public.theme_entities te on te.id = tdv.theme_id
      cross join lateral jsonb_array_elements(coalesce(tdv.author_views_json, '[]'::jsonb)) as view_item(value)
      where coalesce(view_item.value ->> 'stance', '') <> 'mention_only'
        and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
      group by te.theme_key
      order by max(tdv.date_key) desc, count(*) desc
      limit 1
    ) preview;

    if current_uid is null and coalesce(entity_key_arg, '') <> coalesce(preview_key, '') then
      return null;
    end if;

    select jsonb_build_object(
      'key', te.theme_key,
      'display_name', te.display_name,
      'ticker', null,
      'market', null
    )
    into meta_payload
    from public.theme_entities te
    where te.theme_key = entity_key_arg
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
        tdv.date_key,
        tdv.updated_at,
        (
          select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
          from jsonb_array_elements(coalesce(tdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
          where coalesce(view_item.value ->> 'stance', '') <> 'mention_only'
            and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
            and (
              current_uid is null
              or current_is_admin
              or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
                select va.author_name from visible_authors va
              )
            )
        ) as author_views
      from public.theme_daily_views tdv
      join public.theme_entities te on te.id = tdv.theme_id
      where te.theme_key = entity_key_arg
    ),
    visible_days as (
      select *
      from raw_days
      where jsonb_array_length(author_views) > 0
    )
    select count(*)::integer
    into total_count
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
        tdv.date_key,
        tdv.updated_at,
        (
          select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
          from jsonb_array_elements(coalesce(tdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
          where coalesce(view_item.value ->> 'stance', '') <> 'mention_only'
            and lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
            and (
              current_uid is null
              or current_is_admin
              or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
                select va.author_name from visible_authors va
              )
            )
        ) as author_views
      from public.theme_daily_views tdv
      join public.theme_entities te on te.id = tdv.theme_id
      where te.theme_key = entity_key_arg
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

    return jsonb_build_object(
      'meta', meta_payload,
      'timeline', jsonb_build_object(
        'rows', rows_payload,
        'total', total_count,
        'page', safe_page,
        'page_size', safe_page_size,
        'total_pages', greatest(1, ceil(total_count::numeric / safe_page_size)::integer)
      ),
      'chart', null
    );
  end if;

  raise exception 'Unknown entity type.';
end;
$$;

revoke all on function public.get_visible_entity_timeline(text, text, integer, integer) from public;
grant execute on function public.get_visible_entity_timeline(text, text, integer, integer) to anon, authenticated;
