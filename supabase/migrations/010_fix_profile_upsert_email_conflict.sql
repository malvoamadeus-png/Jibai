create or replace function public.upsert_current_profile(
  display_name_arg text default '',
  avatar_url_arg text default ''
)
returns public.profiles
language plpgsql
security definer
set search_path = public
as $$
declare
  result public.profiles;
  current_email citext;
  computed_display_name text;
  existing_profile_id uuid;
begin
  if auth.uid() is null then
    raise exception 'Authentication required.';
  end if;

  current_email := lower(coalesce(auth.jwt() ->> 'email', ''))::citext;
  if current_email::text = '' then
    raise exception 'Authenticated user has no email.';
  end if;

  computed_display_name := nullif(trim(display_name_arg), '');
  if computed_display_name is null then
    computed_display_name := split_part(current_email::text, '@', 1);
  end if;

  select id into existing_profile_id
  from public.profiles
  where email = current_email;

  if existing_profile_id is not null and existing_profile_id <> auth.uid() then
    update public.account_requests set requester_id = auth.uid() where requester_id = existing_profile_id;
    update public.account_requests set reviewed_by = auth.uid() where reviewed_by = existing_profile_id;
    update public.crawl_jobs set requested_by = auth.uid() where requested_by = existing_profile_id;
    update public.user_subscriptions set user_id = auth.uid() where user_id = existing_profile_id;
    update public.x_accounts set approved_by = auth.uid() where approved_by = existing_profile_id;
    update public.x_accounts set submitted_by = auth.uid() where submitted_by = existing_profile_id;

    update public.profiles
    set
      id = auth.uid(),
      display_name = computed_display_name,
      avatar_url = coalesce(avatar_url_arg, ''),
      is_admin = public.is_current_user_admin(),
      updated_at = now()
    where id = existing_profile_id;
  end if;

  insert into public.profiles (id, email, display_name, avatar_url, is_admin, updated_at)
  values (
    auth.uid(),
    current_email,
    computed_display_name,
    coalesce(avatar_url_arg, ''),
    public.is_current_user_admin(),
    now()
  )
  on conflict (id) do update
  set
    email = excluded.email,
    display_name = excluded.display_name,
    avatar_url = excluded.avatar_url,
    is_admin = excluded.is_admin,
    updated_at = now()
  returning * into result;

  return result;
end;
$$;

grant execute on function public.upsert_current_profile(text, text) to authenticated;
