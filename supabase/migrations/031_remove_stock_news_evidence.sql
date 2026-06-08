update public.content_events
set evidence = '',
    updated_at = now()
where analysis_domain = 'stock'
  and evidence <> '';

update public.content_analyses ca
set raw_response_json = jsonb_set(
      coalesce(ca.raw_response_json, '{}'::jsonb),
      '{events}',
      coalesce(
        (
          select jsonb_agg(
            case
              when jsonb_typeof(event_item.value) = 'object' then event_item.value - 'evidence'
              else event_item.value
            end
            order by event_item.ordinality
          )
          from jsonb_array_elements(coalesce(ca.raw_response_json -> 'events', '[]'::jsonb))
            with ordinality as event_item(value, ordinality)
        ),
        '[]'::jsonb
      ),
      true
    ),
    updated_at = now()
where ca.analysis_domain = 'stock'
  and jsonb_typeof(ca.raw_response_json -> 'events') = 'array';

with stripped as (
  select
    snt.date_key,
    coalesce(
      (
        select jsonb_agg(
          case
            when jsonb_typeof(event_item.value) = 'object' then event_item.value - 'evidence'
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
set events_json = stripped.events_json,
    content_hash = md5(
      jsonb_build_object(
        'date', snt.date_key,
        'events', stripped.events_json
      )::text
    ),
    updated_at = now()
from stripped
where stripped.date_key = snt.date_key;
