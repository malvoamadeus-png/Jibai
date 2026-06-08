create table if not exists public.content_events (
  id uuid primary key default gen_random_uuid(),
  content_id uuid not null references public.content_items(id) on delete cascade,
  analysis_domain text not null default 'stock'
    check (analysis_domain = 'stock'),
  headline text not null,
  event_summary text not null default '',
  event_type text not null default 'other',
  event_nature text not null default 'reported',
  evidence text not null default '',
  publish_time timestamptz,
  sort_order integer not null default 0,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists content_events_content_domain_sort
  on public.content_events(content_id, analysis_domain, sort_order);

create index if not exists idx_content_events_domain_content
  on public.content_events(analysis_domain, content_id, sort_order);

create table if not exists public.content_event_entities (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.content_events(id) on delete cascade,
  entity_type text not null
    check (entity_type in ('stock', 'theme')),
  entity_key text not null,
  entity_name text not null,
  entity_code_or_name text,
  security_id uuid references public.security_entities(id) on delete set null,
  theme_id uuid references public.theme_entities(id) on delete set null,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(event_id, entity_type, entity_key)
);

create index if not exists idx_content_event_entities_entity
  on public.content_event_entities(entity_type, entity_key, event_id);

create table if not exists public.stock_news_daily_timeline (
  id uuid primary key default gen_random_uuid(),
  date_key text not null unique,
  event_count integer not null default 0,
  events_json jsonb not null default '[]'::jsonb,
  content_hash text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_stock_news_daily_timeline_date
  on public.stock_news_daily_timeline(date_key desc);

alter table public.content_events enable row level security;
alter table public.content_event_entities enable row level security;
alter table public.stock_news_daily_timeline enable row level security;

drop trigger if exists set_content_events_updated_at on public.content_events;
create trigger set_content_events_updated_at before update on public.content_events
for each row execute function public.set_updated_at();

drop trigger if exists set_content_event_entities_updated_at on public.content_event_entities;
create trigger set_content_event_entities_updated_at before update on public.content_event_entities
for each row execute function public.set_updated_at();

drop trigger if exists set_stock_news_daily_timeline_updated_at on public.stock_news_daily_timeline;
create trigger set_stock_news_daily_timeline_updated_at before update on public.stock_news_daily_timeline
for each row execute function public.set_updated_at();

revoke all on public.content_events from anon, authenticated;
revoke all on public.content_event_entities from anon, authenticated;
revoke all on public.stock_news_daily_timeline from anon, authenticated;

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
        select coalesce(jsonb_agg(event_item.value order by coalesce(event_item.value ->> 'publish_time', '') desc, event_item.ordinality asc), '[]'::jsonb)
        from jsonb_array_elements(coalesce(snt.events_json, '[]'::jsonb)) with ordinality as event_item(value, ordinality)
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
  )
  select count(*)::integer
  into total_count
  from visible_days;

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

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'date', date_key,
        'event_count', event_count,
        'events', events_json,
        'updated_at', updated_at
      )
      order by date_key desc
    ),
    '[]'::jsonb
  )
  into rows_payload
  from (
    select *
    from visible_days
    order by date_key desc
    limit safe_page_size offset offset_value
  ) page_rows;

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
