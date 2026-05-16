-- Restore the public author timeline history after the stock-signal-only RPC
-- migration accidentally limited visible author days to the latest three
-- Shanghai natural days. The worker/backfill keeps a 30-day analysis window;
-- the author list and author timeline RPCs should expose all materialized
-- stock-signal days within that rebuilt window.

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
    where exists (
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

revoke all on function public.list_visible_authors(text, integer) from public;
revoke all on function public.get_visible_author_timeline(uuid, integer, integer) from public;

grant execute on function public.list_visible_authors(text, integer) to anon, authenticated;
grant execute on function public.get_visible_author_timeline(uuid, integer, integer) to anon, authenticated;
