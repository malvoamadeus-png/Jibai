-- Keep the public stock K-line cache to the same 180-day window used by the
-- worker and frontend. Historical rows outside the window are not needed by the
-- chart and make every stock payload heavier.

do $$
declare
  function_sql text;
  old_clause text := 'where security_id = security_id_value;';
  new_clause text := 'where security_id = security_id_value
        and date_key >= (current_date - interval ''180 days'')::date::text;';
  window_clause text := 'date_key >= (current_date - interval ''180 days'')::date::text';
begin
  select pg_get_functiondef('public.get_visible_entity_timeline(text,text,integer,integer)'::regprocedure)
  into function_sql;

  if position(window_clause in function_sql) = 0 then
    if position(old_clause in function_sql) = 0 then
      raise exception 'Could not patch get_visible_entity_timeline stock candle window.';
    end if;

    execute replace(function_sql, old_clause, new_clause);
  end if;
end $$;

delete from public.security_daily_prices
where date_key < (current_date - interval '180 days')::date::text;
