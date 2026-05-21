create table if not exists public.crypto_asset_blocklist (
  term text primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid references auth.users(id) on delete set null
);

create table if not exists public.crypto_asset_admin_deletions (
  asset_key text primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid references auth.users(id) on delete set null,
  reason text not null default ''
);

drop trigger if exists set_crypto_asset_blocklist_updated_at on public.crypto_asset_blocklist;
create trigger set_crypto_asset_blocklist_updated_at before update on public.crypto_asset_blocklist
for each row execute function public.set_updated_at();

drop trigger if exists set_crypto_asset_admin_deletions_updated_at on public.crypto_asset_admin_deletions;
create trigger set_crypto_asset_admin_deletions_updated_at before update on public.crypto_asset_admin_deletions
for each row execute function public.set_updated_at();

revoke all on table public.crypto_asset_blocklist from public;
revoke all on table public.crypto_asset_admin_deletions from public;

insert into public.crypto_asset_blocklist (term)
values ('base')
on conflict (term) do nothing;

create or replace function public.crypto_asset_matches_blocklist(
  asset_key_arg text,
  display_name_arg text,
  symbol_arg text,
  aliases_arg jsonb default '[]'::jsonb
)
returns boolean
language sql
stable
set search_path = public
as $$
  with haystack as (
    select lower(
      concat_ws(
        ' ',
        coalesce(asset_key_arg, ''),
        coalesce(display_name_arg, ''),
        coalesce(symbol_arg, ''),
        coalesce(
          (
            select string_agg(value::text, ' ')
            from jsonb_array_elements_text(coalesce(aliases_arg, '[]'::jsonb)) as value
          ),
          ''
        )
      )
    ) as text_value
  )
  select exists (
    select 1
    from public.crypto_asset_blocklist b
    cross join haystack h
    where nullif(trim(b.term), '') is not null
      and h.text_value like '%' || lower(trim(b.term)) || '%'
  );
$$;

create or replace function public.list_crypto_admin_controls()
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_is_admin boolean := public.is_current_user_admin();
begin
  if not current_is_admin then
    raise exception 'admin only';
  end if;

  return jsonb_build_object(
    'blocked_terms',
    coalesce(
      (
        select jsonb_agg(
          jsonb_build_object(
            'term', term,
            'created_at', created_at,
            'updated_at', updated_at
          )
          order by term asc
        )
        from public.crypto_asset_blocklist
      ),
      '[]'::jsonb
    ),
    'deleted_assets',
    coalesce(
      (
        select jsonb_agg(
          jsonb_build_object(
            'asset_key', d.asset_key,
            'display_name', coalesce(ce.display_name, d.asset_key),
            'reason', d.reason,
            'created_at', d.created_at,
            'updated_at', d.updated_at
          )
          order by d.updated_at desc, d.asset_key asc
        )
        from public.crypto_asset_admin_deletions d
        left join public.crypto_entities ce on ce.asset_key = d.asset_key
      ),
      '[]'::jsonb
    )
  );
end;
$$;

create or replace function public.add_crypto_blocked_term(
  term_arg text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  cleaned text := lower(trim(coalesce(term_arg, '')));
begin
  if not public.is_current_user_admin() then
    raise exception 'admin only';
  end if;
  if cleaned = '' then
    raise exception 'term required';
  end if;

  insert into public.crypto_asset_blocklist(term, created_by)
  values (cleaned, current_uid)
  on conflict (term) do update set updated_at = now();
end;
$$;

create or replace function public.remove_crypto_blocked_term(
  term_arg text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  cleaned text := lower(trim(coalesce(term_arg, '')));
begin
  if not public.is_current_user_admin() then
    raise exception 'admin only';
  end if;
  if cleaned = '' then
    raise exception 'term required';
  end if;

  delete from public.crypto_asset_blocklist
  where term = cleaned;
end;
$$;

create or replace function public.admin_delete_crypto_asset(
  asset_key_arg text,
  reason_arg text default 'deleted_by_admin'
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  cleaned_key text := trim(coalesce(asset_key_arg, ''));
begin
  if not public.is_current_user_admin() then
    raise exception 'admin only';
  end if;
  if cleaned_key = '' then
    raise exception 'asset_key required';
  end if;

  insert into public.crypto_asset_admin_deletions(asset_key, created_by, reason)
  values (cleaned_key, current_uid, left(coalesce(reason_arg, ''), 200))
  on conflict (asset_key) do update set
    updated_at = now(),
    reason = excluded.reason;

  delete from public.crypto_asset_narrative_briefs
  where asset_key = cleaned_key;
end;
$$;

create or replace function public.list_visible_crypto_entities(
  query_arg text default '',
  limit_arg integer default 100,
  sort_arg text default 'date_desc'
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
  safe_sort text;
begin
  safe_limit := case
    when current_uid is null then 1
    else least(greatest(coalesce(limit_arg, 100), 1), 500)
  end;
  safe_sort := case
    when coalesce(sort_arg, '') in ('date_desc', 'date_asc', 'count_desc', 'count_asc') then sort_arg
    else 'date_desc'
  end;

  return query
  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and s.domain = 'crypto'
  ),
  expanded as (
    select
      ce.asset_key::text as key_value,
      ce.display_name::text as display_value,
      ce.symbol::text as ticker_value,
      coalesce(ce.chain, ce.identifier_type)::text as market_value,
      cdv.date_key::text as date_value,
      cdv.updated_at,
      lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as author_name
    from public.crypto_entity_daily_views cdv
    join public.crypto_entities ce on ce.id = cdv.crypto_entity_id
    cross join lateral jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) as view_item(value)
    left join public.crypto_asset_admin_deletions deleted on deleted.asset_key = ce.asset_key
    where public.crypto_view_is_asset_candidate(view_item.value)
      and deleted.asset_key is null
      and not public.crypto_asset_matches_blocklist(ce.asset_key, ce.display_name, ce.symbol, ce.aliases_json)
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
      or lower(coalesce(e.market_value, '')) like '%' || lower(trim(query_arg)) || '%'
    )
  group by e.key_value, e.display_value, e.ticker_value, e.market_value
  order by
    case when safe_sort = 'date_desc' then max(e.date_value) end desc nulls last,
    case when safe_sort = 'date_asc' then max(e.date_value) end asc nulls last,
    case when safe_sort = 'count_desc' then count(*) end desc nulls last,
    case when safe_sort = 'count_asc' then count(*) end asc nulls last,
    e.display_value asc
  limit safe_limit;
end;
$$;

revoke all on function public.crypto_asset_matches_blocklist(text, text, text, jsonb) from public;
revoke all on function public.list_crypto_admin_controls() from public;
revoke all on function public.add_crypto_blocked_term(text) from public;
revoke all on function public.remove_crypto_blocked_term(text) from public;
revoke all on function public.admin_delete_crypto_asset(text, text) from public;
revoke all on function public.list_visible_crypto_entities(text, integer, text) from public;

grant execute on function public.crypto_asset_matches_blocklist(text, text, text, jsonb) to anon, authenticated;
grant execute on function public.list_visible_crypto_entities(text, integer, text) to anon, authenticated;
grant execute on function public.list_crypto_admin_controls() to authenticated;
grant execute on function public.add_crypto_blocked_term(text) to authenticated;
grant execute on function public.remove_crypto_blocked_term(text) to authenticated;
grant execute on function public.admin_delete_crypto_asset(text, text) to authenticated;

create or replace function public.get_visible_crypto_entity_timeline(
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
  entity_id_value uuid;
  meta_payload jsonb;
  rows_payload jsonb;
begin
  safe_page_size := case
    when current_uid is null then least(greatest(coalesce(page_size_arg, 3), 1), 3)
    else least(greatest(coalesce(page_size_arg, 20), 1), 100)
  end;
  offset_value := (safe_page - 1) * safe_page_size;

  select preview.key_value
  into preview_key
  from (
    select
      ce.asset_key::text as key_value,
      max(cdv.date_key) as latest_date,
      count(*) as total_mentions
    from public.crypto_entity_daily_views cdv
    join public.crypto_entities ce on ce.id = cdv.crypto_entity_id
    cross join lateral jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) as view_item(value)
    left join public.crypto_asset_admin_deletions deleted on deleted.asset_key = ce.asset_key
    where lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
      and deleted.asset_key is null
      and not public.crypto_asset_matches_blocklist(ce.asset_key, ce.display_name, ce.symbol, ce.aliases_json)
    group by ce.asset_key
    order by max(cdv.date_key) desc, count(*) desc
    limit 1
  ) preview;

  if current_uid is null and coalesce(entity_key_arg, '') <> coalesce(preview_key, '') then
    return null;
  end if;

  select
    ce.id,
    jsonb_build_object(
      'key', ce.asset_key,
      'display_name', ce.display_name,
      'ticker', ce.symbol,
      'market', coalesce(ce.chain, ce.identifier_type),
      'identifier_type', ce.identifier_type,
      'raw_identifiers', ce.raw_identifiers_json,
      'normalized_status', ce.normalized_status
    )
  into entity_id_value, meta_payload
  from public.crypto_entities ce
  left join public.crypto_asset_admin_deletions deleted on deleted.asset_key = ce.asset_key
  where ce.asset_key = entity_key_arg
    and deleted.asset_key is null
    and not public.crypto_asset_matches_blocklist(ce.asset_key, ce.display_name, ce.symbol, ce.aliases_json)
  limit 1;

  if meta_payload is null then
    return null;
  end if;

  with visible_authors as (
    select lower(xa.username::text) as author_name
    from public.user_subscriptions s
    join public.x_accounts xa on xa.id = s.account_id
    where s.user_id = current_uid
      and s.domain = 'crypto'
  ),
  raw_days as (
    select
      cdv.date_key,
      cdv.updated_at,
      (
        select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
        from jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
        where lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
          and (
            current_uid is null
            or current_is_admin
            or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
              select va.author_name from visible_authors va
            )
          )
      ) as author_views
    from public.crypto_entity_daily_views cdv
    where cdv.crypto_entity_id = entity_id_value
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
      and s.domain = 'crypto'
  ),
  raw_days as (
    select
      cdv.date_key,
      cdv.updated_at,
      (
        select coalesce(jsonb_agg(view_item.value order by view_item.ordinality), '[]'::jsonb)
        from jsonb_array_elements(coalesce(cdv.author_views_json, '[]'::jsonb)) with ordinality as view_item(value, ordinality)
        where lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) <> ''
          and (
            current_uid is null
            or current_is_admin
            or lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) in (
              select va.author_name from visible_authors va
            )
          )
      ) as author_views
    from public.crypto_entity_daily_views cdv
    where cdv.crypto_entity_id = entity_id_value
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
    )
  );
end;
$$;

revoke all on function public.get_visible_crypto_entity_timeline(text, integer, integer) from public;
grant execute on function public.get_visible_crypto_entity_timeline(text, integer, integer) to anon, authenticated;
