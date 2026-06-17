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
  viewer_is_admin boolean := public.is_current_user_admin();
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
                'benefit_layer', sts.raw_payload_json ->> 'benefit_layer',
                'core_link', sts.raw_payload_json ->> 'core_link',
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
    'viewer_is_admin', coalesce(viewer_is_admin, false),
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
