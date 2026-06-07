create table if not exists public.stock_blogger_score_runs (
  id uuid primary key default gen_random_uuid(),
  run_date text not null,
  window_start text not null,
  window_end text not null,
  status text not null default 'running'
    check (status in ('running', 'succeeded', 'failed')),
  config_json jsonb not null default '{}'::jsonb,
  event_count integer not null default 0,
  author_count integer not null default 0,
  error_text text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.stock_blogger_author_scores (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.stock_blogger_score_runs(id) on delete cascade,
  account_id uuid not null references public.x_accounts(id) on delete cascade,
  account_name text not null,
  author_nickname text not null default '',
  overall_score double precision,
  score_1d double precision,
  score_5d double precision,
  score_20d double precision,
  scored_day_count integer not null default 0,
  event_count integer not null default 0,
  scored_event_count integer not null default 0,
  pending_count integer not null default 0,
  positive_count integer not null default 0,
  negative_count integer not null default 0,
  direction_counts_json jsonb not null default '{}'::jsonb,
  conviction_counts_json jsonb not null default '{}'::jsonb,
  score_by_horizon_json jsonb not null default '{}'::jsonb,
  scored_day_count_by_horizon_json jsonb not null default '{}'::jsonb,
  matured_count_by_horizon_json jsonb not null default '{}'::jsonb,
  pending_count_by_horizon_json jsonb not null default '{}'::jsonb,
  best_horizon text,
  worst_horizon text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(run_id, account_id)
);

create table if not exists public.stock_blogger_score_events (
  id uuid primary key default gen_random_uuid(),
  event_key text not null,
  run_id uuid not null references public.stock_blogger_score_runs(id) on delete cascade,
  author_score_id uuid references public.stock_blogger_author_scores(id) on delete cascade,
  account_id uuid not null references public.x_accounts(id) on delete cascade,
  account_name text not null,
  author_nickname text not null default '',
  security_id uuid not null references public.security_entities(id) on delete cascade,
  security_key text not null,
  display_name text not null,
  ticker text,
  market text,
  event_trading_day text not null,
  published_at timestamptz,
  direction text not null,
  conviction text not null default 'unknown',
  evidence_type text not null default 'unknown',
  time_horizons_json jsonb not null default '[]'::jsonb,
  content_ids_json jsonb not null default '[]'::jsonb,
  viewpoint_ids_json jsonb not null default '[]'::jsonb,
  anchor_trading_day text,
  anchor_price double precision,
  anchor_price_kind text,
  benchmark_symbol text,
  benchmark_anchor_price double precision,
  horizon_scores_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists stock_blogger_score_events_run_event_key
  on public.stock_blogger_score_events(run_id, event_key);

create index if not exists idx_stock_blogger_score_runs_status_date
  on public.stock_blogger_score_runs(status, created_at desc);

create index if not exists idx_stock_blogger_author_scores_run_score
  on public.stock_blogger_author_scores(run_id, overall_score desc nulls last);

create index if not exists idx_stock_blogger_score_events_author_day
  on public.stock_blogger_score_events(run_id, account_id, event_trading_day desc);

alter table public.stock_blogger_score_runs enable row level security;
alter table public.stock_blogger_author_scores enable row level security;
alter table public.stock_blogger_score_events enable row level security;

drop trigger if exists set_stock_blogger_score_runs_updated_at on public.stock_blogger_score_runs;
create trigger set_stock_blogger_score_runs_updated_at before update on public.stock_blogger_score_runs
for each row execute function public.set_updated_at();

drop trigger if exists set_stock_blogger_author_scores_updated_at on public.stock_blogger_author_scores;
create trigger set_stock_blogger_author_scores_updated_at before update on public.stock_blogger_author_scores
for each row execute function public.set_updated_at();

drop trigger if exists set_stock_blogger_score_events_updated_at on public.stock_blogger_score_events;
create trigger set_stock_blogger_score_events_updated_at before update on public.stock_blogger_score_events
for each row execute function public.set_updated_at();

revoke all on public.stock_blogger_score_runs from anon, authenticated;
revoke all on public.stock_blogger_author_scores from anon, authenticated;
revoke all on public.stock_blogger_score_events from anon, authenticated;

create or replace function public.get_stock_blogger_gold_rankings()
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  run_row public.stock_blogger_score_runs%rowtype;
  authors_payload jsonb := '[]'::jsonb;
begin
  if current_uid is null then
    return jsonb_build_object(
      'requires_login', true,
      'run', null,
      'authors', '[]'::jsonb
    );
  end if;

  select *
  into run_row
  from public.stock_blogger_score_runs
  where status = 'succeeded'
  order by created_at desc
  limit 1;

  if run_row.id is null then
    return jsonb_build_object(
      'requires_login', false,
      'run', null,
      'authors', '[]'::jsonb
    );
  end if;

  with author_rows as (
    select
      a.*,
      coalesce(
        (
          select jsonb_agg(
            jsonb_build_object(
              'id', e.id::text,
              'security_key', e.security_key,
              'display_name', e.display_name,
              'ticker', e.ticker,
              'market', e.market,
              'event_trading_day', e.event_trading_day,
              'published_at', e.published_at,
              'direction', e.direction,
              'conviction', e.conviction,
              'evidence_type', e.evidence_type,
              'anchor_trading_day', e.anchor_trading_day,
              'anchor_price_kind', e.anchor_price_kind,
              'benchmark_symbol', e.benchmark_symbol,
              'horizon_scores', e.horizon_scores_json
            )
            order by e.event_trading_day desc, e.display_name asc
          )
          from public.stock_blogger_score_events e
          where e.run_id = a.run_id
            and e.account_id = a.account_id
        ),
        '[]'::jsonb
      ) as events_json
    from public.stock_blogger_author_scores a
    where a.run_id = run_row.id
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'account_id', account_id::text,
        'account_name', account_name,
        'author_nickname', author_nickname,
        'overall_score', overall_score,
        'score_1d', score_1d,
        'score_5d', score_5d,
        'score_20d', score_20d,
        'scored_day_count', scored_day_count,
        'event_count', event_count,
        'scored_event_count', scored_event_count,
        'pending_count', pending_count,
        'positive_count', positive_count,
        'negative_count', negative_count,
        'direction_counts', direction_counts_json,
        'conviction_counts', conviction_counts_json,
        'score_by_horizon', score_by_horizon_json,
        'scored_day_count_by_horizon', scored_day_count_by_horizon_json,
        'matured_count_by_horizon', matured_count_by_horizon_json,
        'pending_count_by_horizon', pending_count_by_horizon_json,
        'best_horizon', best_horizon,
        'worst_horizon', worst_horizon,
        'events', events_json
      )
      order by overall_score desc nulls last, account_name asc
    ),
    '[]'::jsonb
  )
  into authors_payload
  from author_rows;

  return jsonb_build_object(
    'requires_login', false,
    'run', jsonb_build_object(
      'id', run_row.id::text,
      'run_date', run_row.run_date,
      'window_start', run_row.window_start,
      'window_end', run_row.window_end,
      'config', run_row.config_json,
      'event_count', run_row.event_count,
      'author_count', run_row.author_count,
      'error_text', run_row.error_text,
      'created_at', run_row.created_at,
      'updated_at', run_row.updated_at
    ),
    'authors', authors_payload
  );
end;
$$;

revoke all on function public.get_stock_blogger_gold_rankings() from public;
revoke all on function public.get_stock_blogger_gold_rankings() from anon;
grant execute on function public.get_stock_blogger_gold_rankings() to authenticated;
