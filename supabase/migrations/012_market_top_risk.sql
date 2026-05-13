create table if not exists public.market_top_risk_snapshots (
  week date primary key,
  nasdaq100 numeric,
  ndx_dd_from_52w_high numeric,
  breadth_weakness_score numeric,
  breakage_score numeric,
  risk_score numeric not null default 0,
  risk_level text not null default 'low',
  warning_active boolean not null default false,
  confirmation_active boolean not null default false,
  signals_json jsonb not null default '{}'::jsonb,
  metrics_json jsonb not null default '{}'::jsonb,
  source_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint market_top_risk_level_check check (risk_level in ('low', 'watch', 'elevated', 'high'))
);

create index if not exists market_top_risk_snapshots_updated_idx
  on public.market_top_risk_snapshots(updated_at desc);

revoke all on table public.market_top_risk_snapshots from public;
grant select on table public.market_top_risk_snapshots to anon, authenticated;

create or replace function public.get_market_top_risk(history_limit_arg integer default 80)
returns jsonb
language plpgsql
security definer
stable
set search_path = public
as $$
declare
  safe_limit integer := least(greatest(coalesce(history_limit_arg, 80), 1), 260);
  latest_payload jsonb;
  history_payload jsonb;
begin
  select jsonb_build_object(
    'week', week,
    'nasdaq100', nasdaq100,
    'ndx_dd_from_52w_high', ndx_dd_from_52w_high,
    'breadth_weakness_score', breadth_weakness_score,
    'breakage_score', breakage_score,
    'risk_score', risk_score,
    'risk_level', risk_level,
    'warning_active', warning_active,
    'confirmation_active', confirmation_active,
    'signals', signals_json,
    'metrics', metrics_json,
    'sources', source_json,
    'updated_at', updated_at
  )
  into latest_payload
  from public.market_top_risk_snapshots
  order by week desc
  limit 1;

  select coalesce(jsonb_agg(row_payload order by week asc), '[]'::jsonb)
  into history_payload
  from (
    select
      week,
      jsonb_build_object(
        'week', week,
        'nasdaq100', nasdaq100,
        'breadth_weakness_score', breadth_weakness_score,
        'breakage_score', breakage_score,
        'risk_score', risk_score,
        'risk_level', risk_level,
        'warning_active', warning_active,
        'confirmation_active', confirmation_active
      ) as row_payload
    from public.market_top_risk_snapshots
    order by week desc
    limit safe_limit
  ) recent_rows;

  return jsonb_build_object(
    'latest', latest_payload,
    'history', history_payload,
    'baseline', jsonb_build_object(
      'near_high_fwd_26w_avg_drawdown', -0.055,
      'near_high_fwd_26w_dd10_probability', 0.211,
      'method', 'Nasdaq 100 within 10% of 52-week high; 26-week forward max drawdown research baseline'
    )
  );
end;
$$;

revoke all on function public.get_market_top_risk(integer) from public;
grant execute on function public.get_market_top_risk(integer) to anon, authenticated;
