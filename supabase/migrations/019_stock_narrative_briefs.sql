create table if not exists public.stock_narrative_briefs (
  id uuid primary key default gen_random_uuid(),
  brief_date date not null unique,
  window_start date,
  window_end date,
  previous_window_start date,
  previous_window_end date,
  baseline_start date,
  baseline_end date,
  status text not null default 'succeeded',
  input_digest_json jsonb not null default '{}'::jsonb,
  brief_sections_json jsonb not null default '{}'::jsonb,
  brief_text text not null default '',
  model_name text,
  prompt_version text not null default 'stock_narrative_v1',
  usage_json jsonb not null default '{}'::jsonb,
  error_text text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint stock_narrative_briefs_status_check check (status in ('succeeded', 'failed', 'skipped'))
);

create index if not exists stock_narrative_briefs_status_date_idx
  on public.stock_narrative_briefs(status, brief_date desc, updated_at desc);

revoke all on table public.stock_narrative_briefs from public;
grant select on table public.stock_narrative_briefs to anon, authenticated;

create or replace function public.get_latest_stock_narrative_brief()
returns jsonb
language sql
security definer
stable
set search_path = public
as $$
  select coalesce(
    (
      select jsonb_build_object(
        'id', id,
        'brief_date', brief_date::text,
        'window_start', window_start::text,
        'window_end', window_end::text,
        'previous_window_start', previous_window_start::text,
        'previous_window_end', previous_window_end::text,
        'baseline_start', baseline_start::text,
        'baseline_end', baseline_end::text,
        'input_digest', input_digest_json,
        'sections', brief_sections_json,
        'brief_text', brief_text,
        'model_name', model_name,
        'prompt_version', prompt_version,
        'usage', usage_json,
        'created_at', created_at,
        'updated_at', updated_at
      )
      from public.stock_narrative_briefs
      where status = 'succeeded'
        and nullif(brief_text, '') is not null
      order by brief_date desc, updated_at desc
      limit 1
    ),
    '{}'::jsonb
  );
$$;

revoke all on function public.get_latest_stock_narrative_brief() from public;
grant execute on function public.get_latest_stock_narrative_brief() to anon, authenticated;
