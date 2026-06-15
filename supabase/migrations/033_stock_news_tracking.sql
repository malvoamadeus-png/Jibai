create table if not exists public.stock_news_tracking (
  id uuid primary key default gen_random_uuid(),
  event_key text not null unique,
  event_date text,
  event_snapshot_json jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'analyzing', 'succeeded', 'failed')),
  selected_by uuid references public.profiles(id) on delete set null,
  analysis_started_at timestamptz,
  analyzed_at timestamptz,
  model_name text,
  request_id text,
  usage_json jsonb not null default '{}'::jsonb,
  raw_response_json jsonb not null default '{}'::jsonb,
  error_text text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.stock_news_tracking_stocks (
  id uuid primary key default gen_random_uuid(),
  tracking_id uuid not null references public.stock_news_tracking(id) on delete cascade,
  sort_order integer not null default 0,
  security_id uuid references public.security_entities(id) on delete set null,
  security_key text not null,
  display_name text not null,
  ticker text,
  market text,
  country_or_region text not null default '',
  benefit_logic text not null default '',
  confidence text not null default 'unknown',
  selected_date text not null,
  anchor_status text not null default 'pending',
  anchor_date text,
  anchor_price numeric,
  latest_date text,
  latest_price numeric,
  horizon_3_status text not null default 'pending',
  return_3d numeric,
  target_3d_date text,
  horizon_7_status text not null default 'pending',
  return_7d numeric,
  target_7d_date text,
  return_since_selected numeric,
  price_status text not null default 'pending'
    check (price_status in ('pending', 'scored', 'missing_price')),
  price_error text not null default '',
  last_price_checked_at timestamptz,
  raw_payload_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(tracking_id, security_key)
);

create index if not exists idx_stock_news_tracking_status_created
  on public.stock_news_tracking(status, created_at);

create index if not exists idx_stock_news_tracking_created
  on public.stock_news_tracking(created_at desc);

create index if not exists idx_stock_news_tracking_stocks_tracking
  on public.stock_news_tracking_stocks(tracking_id, sort_order);

create index if not exists idx_stock_news_tracking_stocks_security
  on public.stock_news_tracking_stocks(security_key);

alter table public.stock_news_tracking enable row level security;
alter table public.stock_news_tracking_stocks enable row level security;

drop trigger if exists set_stock_news_tracking_updated_at on public.stock_news_tracking;
create trigger set_stock_news_tracking_updated_at before update on public.stock_news_tracking
for each row execute function public.set_updated_at();

drop trigger if exists set_stock_news_tracking_stocks_updated_at on public.stock_news_tracking_stocks;
create trigger set_stock_news_tracking_stocks_updated_at before update on public.stock_news_tracking_stocks
for each row execute function public.set_updated_at();

revoke all on public.stock_news_tracking from anon, authenticated;
revoke all on public.stock_news_tracking_stocks from anon, authenticated;

with rebuilt as (
  select
    snt.date_key,
    coalesce(
      (
        select jsonb_agg(
          case
            when jsonb_typeof(event_item.value) = 'object' then
              event_item.value
              || jsonb_build_object(
                'event_sort_order',
                coalesce(nullif(event_item.value ->> 'event_sort_order', '')::integer, (event_item.ordinality - 1)::integer),
                'event_key',
                coalesce(
                  nullif(event_item.value ->> 'event_key', ''),
                  md5(
                    concat_ws(
                      '|',
                      coalesce(event_item.value ->> 'note_id', ''),
                      coalesce(nullif(event_item.value ->> 'event_sort_order', ''), ((event_item.ordinality - 1)::integer)::text),
                      coalesce(event_item.value ->> 'headline', '')
                    )
                  )
                )
              )
            else event_item.value
          end
          order by event_item.ordinality
        )
        from jsonb_array_elements(coalesce(snt.events_json, '[]'::jsonb))
          with ordinality as event_item(value, ordinality)
      ),
      '[]'::jsonb
    ) as events_json
  from public.stock_news_daily_timeline snt
)
update public.stock_news_daily_timeline snt
set events_json = rebuilt.events_json,
    content_hash = md5(jsonb_build_object('date', snt.date_key, 'events', rebuilt.events_json)::text),
    updated_at = now()
from rebuilt
where rebuilt.date_key = snt.date_key;

create or replace function public.track_stock_news_event(
  event_key_arg text,
  event_snapshot_arg jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  safe_event_key text := nullif(trim(coalesce(event_key_arg, '')), '');
  safe_snapshot jsonb := coalesce(event_snapshot_arg, '{}'::jsonb);
  tracking_row public.stock_news_tracking%rowtype;
begin
  if current_uid is null or not public.is_current_user_admin() then
    raise exception 'Only admins can track stock news events' using errcode = '42501';
  end if;
  if safe_event_key is null then
    raise exception 'event_key is required' using errcode = '22023';
  end if;

  safe_snapshot := safe_snapshot || jsonb_build_object('event_key', safe_event_key);

  insert into public.stock_news_tracking (
    event_key, event_date, event_snapshot_json, selected_by, status, updated_at
  )
  values (
    safe_event_key,
    nullif(safe_snapshot ->> 'date', ''),
    safe_snapshot,
    current_uid,
    'pending',
    now()
  )
  on conflict (event_key) do update set
    event_snapshot_json = public.stock_news_tracking.event_snapshot_json || excluded.event_snapshot_json,
    event_date = coalesce(public.stock_news_tracking.event_date, excluded.event_date),
    updated_at = now()
  returning *
  into tracking_row;

  return jsonb_build_object(
    'id', tracking_row.id,
    'event_key', tracking_row.event_key,
    'status', tracking_row.status,
    'created_at', tracking_row.created_at,
    'updated_at', tracking_row.updated_at
  );
end;
$$;

revoke all on function public.track_stock_news_event(text, jsonb) from public;
grant execute on function public.track_stock_news_event(text, jsonb) to authenticated;

create or replace function public.get_stock_news_tracking(
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
  safe_page integer := greatest(coalesce(page_arg, 1), 1);
  safe_page_size integer := least(greatest(coalesce(page_size_arg, 20), 1), 100);
  offset_value integer := (greatest(coalesce(page_arg, 1), 1) - 1) * least(greatest(coalesce(page_size_arg, 20), 1), 100);
  total_count integer := 0;
  rows_payload jsonb := '[]'::jsonb;
begin
  select count(*)::integer
  into total_count
  from public.stock_news_tracking;

  with page_rows as (
    select *
    from public.stock_news_tracking
    order by created_at desc
    limit safe_page_size offset offset_value
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'id', pr.id,
        'event_key', pr.event_key,
        'event_date', pr.event_date,
        'event_snapshot', pr.event_snapshot_json,
        'status', pr.status,
        'model_name', pr.model_name,
        'error_text', pr.error_text,
        'created_at', pr.created_at,
        'analyzed_at', pr.analyzed_at,
        'stocks', coalesce(
          (
            select jsonb_agg(
              jsonb_build_object(
                'id', sts.id,
                'sort_order', sts.sort_order,
                'security_key', sts.security_key,
                'display_name', sts.display_name,
                'ticker', sts.ticker,
                'market', sts.market,
                'country_or_region', sts.country_or_region,
                'benefit_logic', sts.benefit_logic,
                'confidence', sts.confidence,
                'selected_date', sts.selected_date,
                'anchor_status', sts.anchor_status,
                'anchor_date', sts.anchor_date,
                'anchor_price', sts.anchor_price,
                'latest_date', sts.latest_date,
                'latest_price', sts.latest_price,
                'horizon_3_status', sts.horizon_3_status,
                'return_3d', sts.return_3d,
                'target_3d_date', sts.target_3d_date,
                'horizon_7_status', sts.horizon_7_status,
                'return_7d', sts.return_7d,
                'target_7d_date', sts.target_7d_date,
                'return_since_selected', sts.return_since_selected,
                'price_status', sts.price_status,
                'price_error', sts.price_error,
                'last_price_checked_at', sts.last_price_checked_at
              )
              order by sts.sort_order asc, sts.display_name asc
            )
            from public.stock_news_tracking_stocks sts
            where sts.tracking_id = pr.id
          ),
          '[]'::jsonb
        )
      )
      order by pr.created_at desc
    ),
    '[]'::jsonb
  )
  into rows_payload
  from page_rows pr;

  return jsonb_build_object(
    'tracking', jsonb_build_object(
      'rows', rows_payload,
      'total', total_count,
      'page', safe_page,
      'page_size', safe_page_size,
      'total_pages', greatest(1, ceil(total_count::numeric / safe_page_size)::integer)
    )
  );
end;
$$;

revoke all on function public.get_stock_news_tracking(integer, integer) from public;
grant execute on function public.get_stock_news_tracking(integer, integer) to anon, authenticated;

create or replace function public.get_visible_stock_news_timeline(
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
  preview_date text;
  total_count integer := 0;
  rows_payload jsonb := '[]'::jsonb;
begin
  safe_page_size := case
    when current_uid is null then least(greatest(coalesce(page_size_arg, 3), 1), 3)
    else least(greatest(coalesce(page_size_arg, 20), 1), 100)
  end;
  offset_value := (safe_page - 1) * safe_page_size;

  select max(date_key)
  into preview_date
  from public.stock_news_daily_timeline;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    join public.account_domains ad on ad.account_id = xa.id and ad.domain = 'stock'
    where s.user_id = current_uid
      and s.domain = 'stock'
      and ad.status = 'approved'
  ),
  raw_days as (
    select
      snt.date_key,
      snt.updated_at,
      (
        select coalesce(
          jsonb_agg(
            enriched.event_value
            order by coalesce(enriched.event_value ->> 'publish_time', '') desc, event_item.ordinality asc
          ),
          '[]'::jsonb
        )
        from jsonb_array_elements(coalesce(snt.events_json, '[]'::jsonb)) with ordinality as event_item(value, ordinality)
        cross join lateral (
          select
            coalesce(
              nullif(event_item.value ->> 'event_key', ''),
              md5(
                concat_ws(
                  '|',
                  coalesce(event_item.value ->> 'note_id', ''),
                  coalesce(nullif(event_item.value ->> 'event_sort_order', ''), ((event_item.ordinality - 1)::integer)::text),
                  coalesce(event_item.value ->> 'headline', '')
                )
              )
            ) as event_key,
            coalesce(nullif(event_item.value ->> 'event_sort_order', '')::integer, (event_item.ordinality - 1)::integer) as event_sort_order
        ) event_meta
        cross join lateral (
          select
            event_item.value
            || jsonb_build_object(
              'event_key', event_meta.event_key,
              'event_sort_order', event_meta.event_sort_order,
              'is_tracked', exists (
                select 1
                from public.stock_news_tracking sntk
                where sntk.event_key = event_meta.event_key
              )
            ) as event_value
        ) enriched
        where coalesce(event_item.value ->> 'account_name', '') <> ''
          and (
            current_uid is null
            or current_is_admin
            or lower(regexp_replace(coalesce(event_item.value ->> 'account_name', ''), '^@', '')) in (
              select va.author_name from visible_authors va
            )
          )
      ) as events_json
    from public.stock_news_daily_timeline snt
    where current_uid is not null
       or snt.date_key = preview_date
  ),
  visible_days as (
    select
      date_key,
      updated_at,
      events_json,
      jsonb_array_length(events_json) as event_count
    from raw_days
    where jsonb_array_length(events_json) > 0
  ),
  page_rows as (
    select *
    from visible_days
    order by date_key desc
    limit safe_page_size offset offset_value
  )
  select
    coalesce((select count(*)::integer from visible_days), 0),
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'date', page_rows.date_key,
          'event_count', page_rows.event_count,
          'events', page_rows.events_json,
          'updated_at', page_rows.updated_at
        )
        order by page_rows.date_key desc
      ),
      '[]'::jsonb
    )
  into total_count, rows_payload
  from page_rows;

  if total_count = 0 then
    return jsonb_build_object(
      'timeline', jsonb_build_object(
        'rows', '[]'::jsonb,
        'total', 0,
        'page', safe_page,
        'page_size', safe_page_size,
        'total_pages', 1
      )
    );
  end if;

  return jsonb_build_object(
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

revoke all on function public.get_visible_stock_news_timeline(integer, integer) from public;
grant execute on function public.get_visible_stock_news_timeline(integer, integer) to anon, authenticated;
