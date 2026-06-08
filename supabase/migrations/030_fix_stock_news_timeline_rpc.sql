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
            event_item.value
            order by coalesce(event_item.value ->> 'publish_time', '') desc, event_item.ordinality asc
          ),
          '[]'::jsonb
        )
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
