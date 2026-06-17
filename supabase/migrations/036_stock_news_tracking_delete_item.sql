create or replace function public.delete_stock_news_tracking_item(
  tracking_id_arg uuid
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  current_uid uuid := auth.uid();
  deleted_row record;
begin
  if current_uid is null or not public.is_current_user_admin() then
    raise exception 'Only admins can delete tracked stock news items' using errcode = '42501';
  end if;

  delete from public.stock_news_tracking
  where id = tracking_id_arg
  returning id, event_key
  into deleted_row;

  if not found then
    raise exception 'tracked stock news item not found' using errcode = '02000';
  end if;

  return jsonb_build_object(
    'id', deleted_row.id,
    'event_key', deleted_row.event_key,
    'deleted', true
  );
end;
$$;

revoke all on function public.delete_stock_news_tracking_item(uuid) from public;
grant execute on function public.delete_stock_news_tracking_item(uuid) to authenticated;
