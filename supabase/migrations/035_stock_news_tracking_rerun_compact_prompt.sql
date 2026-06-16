delete from public.stock_news_tracking_stocks;

update public.stock_news_tracking
set status = 'pending',
    analysis_started_at = null,
    analyzed_at = null,
    model_name = null,
    request_id = null,
    usage_json = '{}'::jsonb,
    raw_response_json = '{}'::jsonb,
    error_text = '',
    updated_at = now();

