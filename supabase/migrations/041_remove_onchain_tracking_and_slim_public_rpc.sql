-- Remove the retired public onchain wallet-tracking surface and shrink the
-- largest public JSON RPC payloads without rewriting materialized source rows.

drop function if exists public.list_onchain_admin_dashboard();
drop function if exists public.get_onchain_overview();
drop function if exists public.get_onchain_wallet_matrix(uuid, text, text[]);
drop function if exists public.get_onchain_token_matrix(text, text[]);
drop function if exists public.list_my_onchain_wallet_requests();
drop function if exists public.enqueue_onchain_fetch();
drop function if exists public.admin_update_onchain_wallet(uuid, text, text[], text);
drop function if exists public.reject_onchain_wallet_request(uuid);
drop function if exists public.approve_onchain_wallet_request(uuid);
drop function if exists public.set_onchain_wallet_note(uuid, text);
drop function if exists public.set_onchain_wallet_subscription(uuid, boolean);
drop function if exists public.submit_onchain_wallet(text, text[]);
drop function if exists public.list_onchain_wallets(text, integer);
drop function if exists public.onchain_visible_wallet_ids();
drop function if exists public.onchain_chain_index(text);
drop function if exists public.onchain_short_address(text);
drop function if exists public.onchain_normalize_address(text);

drop table if exists public.onchain_daily_token_views cascade;
drop table if exists public.onchain_daily_wallet_token_views cascade;
drop table if exists public.onchain_balance_snapshots cascade;
drop table if exists public.onchain_fetch_run_items cascade;
drop table if exists public.onchain_fetch_runs cascade;
drop table if exists public.onchain_token_filter_rules cascade;
drop table if exists public.onchain_user_wallet_notes cascade;
drop table if exists public.onchain_user_wallet_subscriptions cascade;
drop table if exists public.onchain_wallet_requests cascade;
drop table if exists public.onchain_wallet_chains cascade;
drop table if exists public.onchain_tokens cascade;
drop table if exists public.onchain_wallets cascade;

create or replace function public.slim_stock_author_view(view_value jsonb)
returns jsonb
language sql
immutable
as $$
  select jsonb_build_object(
    'platform', coalesce(view_value ->> 'platform', 'x'),
    'account_name', lower(regexp_replace(coalesce(view_value ->> 'account_name', view_value ->> 'author_name', view_value ->> 'username', ''), '^@', '')),
    'author_nickname', coalesce(view_value ->> 'author_nickname', view_value ->> 'display_name', ''),
    'stance', coalesce(view_value ->> 'stance', 'unknown'),
    'direction', coalesce(view_value ->> 'direction', 'unknown'),
    'signal_type', coalesce(view_value ->> 'signal_type', 'unknown'),
    'judgment_type', coalesce(view_value ->> 'judgment_type', 'unknown'),
    'conviction', coalesce(view_value ->> 'conviction', 'unknown'),
    'evidence_type', coalesce(view_value ->> 'evidence_type', 'unknown'),
    'logic', coalesce(view_value ->> 'logic', ''),
    'evidence', coalesce(view_value -> 'evidence', '[]'::jsonb),
    'note_ids', coalesce(view_value -> 'note_ids', '[]'::jsonb),
    'note_urls', coalesce(view_value -> 'note_urls', '[]'::jsonb)
  );
$$;

create or replace function public.slim_stock_news_event(event_value jsonb)
returns jsonb
language sql
immutable
as $$
  select jsonb_strip_nulls(jsonb_build_object(
    'event_key', event_value ->> 'event_key',
    'event_sort_order', event_value -> 'event_sort_order',
    'note_id', event_value ->> 'note_id',
    'note_url', event_value ->> 'note_url',
    'note_title', event_value ->> 'note_title',
    'account_name', event_value ->> 'account_name',
    'author_nickname', event_value ->> 'author_nickname',
    'publish_time', event_value ->> 'publish_time',
    'headline', event_value ->> 'headline',
    'event_summary', event_value ->> 'event_summary',
    'event_type', coalesce(event_value ->> 'event_type', 'other'),
    'event_nature', coalesce(event_value ->> 'event_nature', 'reported'),
    'linked_entities', coalesce(event_value -> 'linked_entities', '[]'::jsonb),
    'is_tracked', coalesce(event_value -> 'is_tracked', 'false'::jsonb)
  ));
$$;

do $$
declare
  function_sql text;
begin
  function_sql := pg_get_functiondef('public.get_visible_entity_timeline(text,text,integer,integer)'::regprocedure);
  function_sql := replace(
    function_sql,
    'jsonb_agg(view_item.value order by view_item.ordinality)',
    'jsonb_agg(public.slim_stock_author_view(view_item.value) order by view_item.ordinality)'
  );
  execute function_sql;
end $$;

do $$
declare
  function_sql text;
begin
  function_sql := pg_get_functiondef('public.get_visible_stock_news_timeline(integer,integer)'::regprocedure);
  function_sql := replace(
    function_sql,
    'event_item.value
            order by coalesce(event_item.value ->> ''publish_time'', '''') desc, event_item.ordinality asc',
    'public.slim_stock_news_event(event_item.value)
            order by coalesce(event_item.value ->> ''publish_time'', '''') desc, event_item.ordinality asc'
  );
  execute function_sql;
end $$;

do $$
declare
  function_sql text;
begin
  function_sql := pg_get_functiondef('public.get_visible_stock_matrix(text,text)'::regprocedure);
  function_sql := replace(
    function_sql,
    '''logic'', coalesce(view_value ->> ''logic'', ''''),
          ''evidence'', coalesce(view_value -> ''evidence'', ''[]''::jsonb),
          ''note_ids'', coalesce(view_value -> ''note_ids'', ''[]''::jsonb),
          ''note_urls'', coalesce(view_value -> ''note_urls'', ''[]''::jsonb),
          ''time_horizons'', coalesce(view_value -> ''time_horizons'', ''[]''::jsonb)',
    '''logic'', coalesce(view_value ->> ''logic'', ''''),
          ''evidence'', coalesce(view_value -> ''evidence'', ''[]''::jsonb),
          ''note_urls'', coalesce(view_value -> ''note_urls'', ''[]''::jsonb)'
  );
  execute function_sql;
end $$;

do $$
declare
  function_sql text;
begin
  function_sql := pg_get_functiondef('public.get_visible_crypto_matrix(text,text)'::regprocedure);
  function_sql := replace(
    function_sql,
    '''logic'', coalesce(view_value ->> ''logic'', ''''),
          ''evidence'', coalesce(view_value -> ''evidence'', ''[]''::jsonb),
          ''note_ids'', coalesce(view_value -> ''note_ids'', ''[]''::jsonb),
          ''note_urls'', coalesce(view_value -> ''note_urls'', ''[]''::jsonb),
          ''time_horizons'', coalesce(view_value -> ''time_horizons'', ''[]''::jsonb),
          ''metadata'', coalesce(view_value -> ''metadata'', ''{}''::jsonb)',
    '''logic'', coalesce(view_value ->> ''logic'', ''''),
          ''evidence'', coalesce(view_value -> ''evidence'', ''[]''::jsonb),
          ''note_urls'', coalesce(view_value -> ''note_urls'', ''[]''::jsonb),
          ''metadata'', jsonb_strip_nulls(jsonb_build_object(
            ''resolver_strategy'', view_value #> ''{metadata,resolver_strategy}'',
            ''match_confidence'', view_value #> ''{metadata,match_confidence}''
          ))'
  );
  execute function_sql;
end $$;
