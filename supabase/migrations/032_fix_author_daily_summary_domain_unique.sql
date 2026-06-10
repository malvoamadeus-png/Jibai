-- Align author_daily_summaries with the domain-aware upsert path used by the
-- public worker. Without this unique index, stock author timelines cannot be
-- materialized with ON CONFLICT(account_id, date_key, analysis_domain).

create unique index if not exists idx_author_daily_summaries_account_date_domain
  on public.author_daily_summaries(account_id, date_key, analysis_domain);
