-- Fix known stock identity mistakes seen in public X analysis.
-- These updates are idempotent and keep existing rows/FKs in place where possible.

update public.security_entities
set security_key = 'intel'
where security_key = 'intc'
  and not exists (
    select 1 from public.security_entities existing
    where existing.security_key = 'intel'
  );

update public.security_entities
set
  display_name = 'Intel',
  ticker = 'INTC',
  market = 'NASDAQ',
  aliases_json = '["Intel", "英特尔", "INTC", "Intel Foundry", "Intel Foundry Services", "IFS"]'::jsonb,
  updated_at = now()
where security_key = 'intel'
   or lower(display_name) in ('intel', 'intel foundry', 'intel foundry services', 'ifs')
   or upper(coalesce(ticker, '')) = 'INTEL';

update public.content_viewpoints
set
  entity_key = 'intel',
  entity_name = 'Intel',
  entity_code_or_name = 'INTC',
  updated_at = now()
where entity_type = 'stock'
  and (
    entity_key in ('intel', 'intc')
    or lower(entity_name) in ('intel', 'intel foundry', 'intel foundry services', 'ifs')
    or upper(coalesce(entity_code_or_name, '')) in ('INTEL', 'INTC', 'IFS')
  );

update public.security_mentions
set
  stock_name = 'Intel',
  raw_name = case when upper(raw_name) in ('INTEL', 'IFS') then 'INTC' else raw_name end,
  updated_at = now()
where lower(coalesce(stock_name, '')) in ('intel', 'intel foundry', 'intel foundry services', 'ifs')
   or upper(raw_name) in ('INTEL', 'INTC', 'IFS');

update public.security_entities
set security_key = '6451.tw'
where security_key = '6451'
  and not exists (
    select 1 from public.security_entities existing
    where existing.security_key = '6451.tw'
  );

update public.security_entities
set
  display_name = 'Shunsin',
  ticker = '6451',
  market = 'TWSE',
  aliases_json = '["Shunsin", "Shunsin Technology", "訊芯", "訊芯-KY", "6451", "6451.TW"]'::jsonb,
  updated_at = now()
where security_key in ('6451', '6451.tw', 'shunsin')
   or lower(display_name) = 'shunsin'
   or display_name in ('訊芯', '訊芯-KY')
   or ticker = '6451';

update public.content_viewpoints
set
  entity_key = '6451.tw',
  entity_name = 'Shunsin',
  entity_code_or_name = '6451.TW',
  updated_at = now()
where entity_type = 'stock'
  and (
    entity_key in ('6451', '6451.tw', 'shunsin')
    or entity_name in ('6451', 'Shunsin', '訊芯', '訊芯-KY')
    or upper(coalesce(entity_code_or_name, '')) in ('6451', '6451.TW')
  );

update public.security_mentions
set
  stock_name = 'Shunsin',
  raw_name = case when raw_name = '6451' then '6451.TW' else raw_name end,
  updated_at = now()
where raw_name in ('6451', '6451.TW')
   or stock_name in ('6451', 'Shunsin', '訊芯', '訊芯-KY');

update public.security_entities
set security_key = 'sivers'
where security_key = 'sive'
  and not exists (
    select 1 from public.security_entities existing
    where existing.security_key = 'sivers'
  );

update public.security_entities
set
  display_name = 'Sivers',
  ticker = 'SIVE',
  market = 'STO',
  aliases_json = '["Sivers", "Sivers Semiconductors", "SIVE"]'::jsonb,
  updated_at = now()
where security_key in ('sive', 'sivers')
   or lower(display_name) in ('sivers', 'sivers semiconductors', 'silexion')
   or upper(coalesce(ticker, '')) = 'SIVE';

update public.content_viewpoints
set
  entity_key = 'sivers',
  entity_name = 'Sivers',
  entity_code_or_name = 'SIVE.ST',
  updated_at = now()
where entity_type = 'stock'
  and (
    entity_key in ('sive', 'sivers')
    or lower(entity_name) in ('sivers', 'sivers semiconductors', 'silexion')
    or upper(coalesce(entity_code_or_name, '')) in ('SIVE', 'SIVE.ST')
  );

update public.security_mentions
set
  stock_name = 'Sivers',
  raw_name = case when upper(raw_name) = 'SIVE' then 'SIVE.ST' else raw_name end,
  updated_at = now()
where lower(coalesce(stock_name, '')) in ('sivers', 'sivers semiconductors', 'silexion')
   or upper(raw_name) in ('SIVE', 'SIVE.ST');
