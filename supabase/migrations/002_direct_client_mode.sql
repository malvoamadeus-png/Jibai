-- Direct browser-client mode for public-web.
-- Run this after 001_public_schema.sql when the Vercel app should talk to Supabase
-- with only NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
--
-- Bootstrap admins manually in Supabase SQL editor after applying this migration:
-- insert into public.admin_emails(email) values ('you@example.com') on conflict do nothing;

create table if not exists public.admin_emails (
  email citext primary key,
  created_at timestamptz not null default now()
);

alter table public.admin_emails enable row level security;

create or replace function public.is_current_user_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1
    from public.admin_emails
    where email = lower(coalesce(auth.jwt() ->> 'email', ''))::citext
  );
$$;

grant execute on function public.is_current_user_admin() to authenticated;

drop policy if exists "admin emails readable by admins" on public.admin_emails;
create policy "admin emails readable by admins" on public.admin_emails
for select to authenticated using (public.is_current_user_admin());

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

drop policy if exists "profiles owner read" on public.profiles;
drop policy if exists "profiles owner update" on public.profiles;
drop policy if exists "profiles direct read" on public.profiles;
create policy "profiles direct read" on public.profiles
for select to authenticated using (id = auth.uid() or public.is_current_user_admin());

drop policy if exists "profiles direct insert" on public.profiles;
create policy "profiles direct insert" on public.profiles
for insert to authenticated
with check (
  id = auth.uid()
  and lower(email::text) = lower(coalesce(auth.jwt() ->> 'email', ''))
  and is_admin = public.is_current_user_admin()
);

drop policy if exists "profiles direct update" on public.profiles;
create policy "profiles direct update" on public.profiles
for update to authenticated
using (id = auth.uid())
with check (
  id = auth.uid()
  and lower(email::text) = lower(coalesce(auth.jwt() ->> 'email', ''))
  and is_admin = public.is_current_user_admin()
);

drop policy if exists "approved accounts readable" on public.x_accounts;
drop policy if exists "x accounts direct read" on public.x_accounts;
create policy "x accounts direct read" on public.x_accounts
for select to authenticated using (status = 'approved' or public.is_current_user_admin());

drop policy if exists "own requests readable" on public.account_requests;
drop policy if exists "account requests direct read" on public.account_requests;
create policy "account requests direct read" on public.account_requests
for select to authenticated using (requester_id = auth.uid() or public.is_current_user_admin());

drop policy if exists "own subscriptions readable" on public.user_subscriptions;
drop policy if exists "subscriptions direct read" on public.user_subscriptions;
create policy "subscriptions direct read" on public.user_subscriptions
for select to authenticated using (user_id = auth.uid() or public.is_current_user_admin());

drop policy if exists "subscriptions direct insert" on public.user_subscriptions;
create policy "subscriptions direct insert" on public.user_subscriptions
for insert to authenticated
with check (
  user_id = auth.uid()
  and exists (
    select 1
    from public.x_accounts
    where x_accounts.id = account_id
      and x_accounts.status = 'approved'
  )
);

drop policy if exists "subscriptions direct delete" on public.user_subscriptions;
create policy "subscriptions direct delete" on public.user_subscriptions
for delete to authenticated using (user_id = auth.uid());

drop policy if exists "content items subscribed read" on public.content_items;
create policy "content items subscribed read" on public.content_items
for select to authenticated using (
  public.is_current_user_admin()
  or exists (
    select 1
    from public.user_subscriptions
    where user_subscriptions.user_id = auth.uid()
      and user_subscriptions.account_id = content_items.account_id
  )
);

drop policy if exists "author summaries subscribed read" on public.author_daily_summaries;
create policy "author summaries subscribed read" on public.author_daily_summaries
for select to authenticated using (
  public.is_current_user_admin()
  or exists (
    select 1
    from public.user_subscriptions
    where user_subscriptions.user_id = auth.uid()
      and user_subscriptions.account_id = author_daily_summaries.account_id
  )
);

drop policy if exists "content analyses subscribed read" on public.content_analyses;
create policy "content analyses subscribed read" on public.content_analyses
for select to authenticated using (
  public.is_current_user_admin()
  or exists (
    select 1
    from public.content_items
    join public.user_subscriptions on user_subscriptions.account_id = content_items.account_id
    where content_items.id = content_analyses.content_id
      and user_subscriptions.user_id = auth.uid()
  )
);

drop policy if exists "content viewpoints subscribed read" on public.content_viewpoints;
create policy "content viewpoints subscribed read" on public.content_viewpoints
for select to authenticated using (
  public.is_current_user_admin()
  or exists (
    select 1
    from public.content_items
    join public.user_subscriptions on user_subscriptions.account_id = content_items.account_id
    where content_items.id = content_viewpoints.content_id
      and user_subscriptions.user_id = auth.uid()
  )
);

alter table public.security_mentions enable row level security;

drop policy if exists "security mentions subscribed read" on public.security_mentions;
create policy "security mentions subscribed read" on public.security_mentions
for select to authenticated using (
  public.is_current_user_admin()
  or exists (
    select 1
    from public.content_items
    join public.user_subscriptions on user_subscriptions.account_id = content_items.account_id
    where content_items.id = security_mentions.content_id
      and user_subscriptions.user_id = auth.uid()
  )
);

drop policy if exists "security entities readable" on public.security_entities;
create policy "security entities readable" on public.security_entities
for select to authenticated using (true);

drop policy if exists "theme entities readable" on public.theme_entities;
create policy "theme entities readable" on public.theme_entities
for select to authenticated using (true);

create or replace function public.submit_x_account(raw_input_arg text, username_arg text)
returns table (
  account_id uuid,
  request_id uuid,
  account_status text,
  request_status text
)
language plpgsql
security definer
set search_path = public
as $$
declare
  account_id_value uuid;
  request_id_value uuid;
  account_status_value text;
  request_status_value text;
  normalized_username citext;
begin
  if auth.uid() is null then
    raise exception 'Authentication required.';
  end if;

  normalized_username := lower(trim(username_arg))::citext;
  if normalized_username::text !~ '^[a-z0-9_]{1,15}$' then
    raise exception 'Invalid X username.';
  end if;

  select id, status
  into account_id_value, account_status_value
  from public.x_accounts
  where username = normalized_username;

  if account_id_value is null then
    insert into public.x_accounts (username, display_name, profile_url, status, submitted_by)
    values (
      normalized_username,
      normalized_username::text,
      'https://x.com/' || normalized_username::text,
      'pending',
      auth.uid()
    )
    returning id, status into account_id_value, account_status_value;
  end if;

  request_status_value := case when account_status_value = 'approved' then 'approved' else 'pending' end;

  insert into public.account_requests (
    account_id,
    requester_id,
    raw_input,
    normalized_username,
    status,
    reviewed_at
  )
  values (
    account_id_value,
    auth.uid(),
    raw_input_arg,
    normalized_username,
    request_status_value,
    case when request_status_value = 'approved' then now() else null end
  )
  on conflict (account_id, requester_id) do update
  set
    raw_input = excluded.raw_input,
    normalized_username = excluded.normalized_username,
    status = excluded.status,
    reviewed_at = excluded.reviewed_at,
    updated_at = now()
  returning id into request_id_value;

  if account_status_value = 'approved' then
    insert into public.user_subscriptions (user_id, account_id)
    values (auth.uid(), account_id_value)
    on conflict do nothing;
  end if;

  return query select account_id_value, request_id_value, account_status_value, request_status_value;
end;
$$;

grant execute on function public.submit_x_account(text, text) to authenticated;

create or replace function public.approve_account_request(request_id_arg uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  account_id_value uuid;
  existing_status text;
  approved_count integer;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin access required.';
  end if;

  select account_id
  into account_id_value
  from public.account_requests
  where id = request_id_arg;

  if account_id_value is null then
    raise exception 'Request not found.';
  end if;

  select status into existing_status
  from public.x_accounts
  where id = account_id_value;

  if existing_status is distinct from 'approved' then
    select count(*) into approved_count
    from public.x_accounts
    where status = 'approved';

    if approved_count >= 100 then
      raise exception 'Approved X account limit reached.';
    end if;
  end if;

  update public.x_accounts
  set
    status = 'approved',
    approved_by = auth.uid(),
    approved_at = now(),
    rejected_at = null,
    disabled_at = null
  where id = account_id_value;

  update public.account_requests
  set
    status = 'approved',
    reviewed_by = auth.uid(),
    reviewed_at = now()
  where account_id = account_id_value
    and status = 'pending';

  insert into public.user_subscriptions (user_id, account_id)
  select requester_id, account_id_value
  from public.account_requests
  where account_id = account_id_value
    and status = 'approved'
  on conflict do nothing;
end;
$$;

grant execute on function public.approve_account_request(uuid) to authenticated;

create or replace function public.reject_account_request(request_id_arg uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  account_id_value uuid;
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin access required.';
  end if;

  select account_id
  into account_id_value
  from public.account_requests
  where id = request_id_arg;

  if account_id_value is null then
    raise exception 'Request not found.';
  end if;

  update public.account_requests
  set
    status = 'rejected',
    reviewed_by = auth.uid(),
    reviewed_at = now()
  where account_id = account_id_value
    and status = 'pending';

  update public.x_accounts
  set
    status = 'rejected',
    rejected_at = now()
  where id = account_id_value
    and status = 'pending';
end;
$$;

grant execute on function public.reject_account_request(uuid) to authenticated;

create or replace function public.disable_x_account(account_id_arg uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_current_user_admin() then
    raise exception 'Admin access required.';
  end if;

  update public.x_accounts
  set
    status = 'disabled',
    disabled_at = now()
  where id = account_id_arg;
end;
$$;

grant execute on function public.disable_x_account(uuid) to authenticated;

create or replace function public.list_my_entities(entity_type_arg text)
returns table (
  entity_key text,
  display_name text,
  latest_date text,
  mention_count integer,
  author_count integer
)
language plpgsql
security definer
stable
set search_path = public
as $$
begin
  if auth.uid() is null then
    raise exception 'Authentication required.';
  end if;

  if entity_type_arg = 'stock' then
    return query
    with expanded as (
      select
        security_entities.security_key::text as key_value,
        security_entities.display_name::text as display_value,
        security_daily_views.date_key::text as date_value,
        lower(coalesce(view_item ->> 'account_name', view_item ->> 'author_name', view_item ->> 'username', '')) as author_name
      from public.security_daily_views
      join public.security_entities on security_entities.id = security_daily_views.security_id
      cross join lateral jsonb_array_elements(coalesce(security_daily_views.author_views_json, '[]'::jsonb)) as view_item
    )
    select
      key_value,
      display_value,
      max(date_value)::text,
      count(*)::integer,
      count(distinct author_name)::integer
    from expanded
    where author_name <> ''
      and (
        public.is_current_user_admin()
        or author_name in (
          select lower(x_accounts.username::text)
          from public.user_subscriptions
          join public.x_accounts on x_accounts.id = user_subscriptions.account_id
          where user_subscriptions.user_id = auth.uid()
        )
      )
    group by key_value, display_value
    order by max(date_value) desc, count(*) desc
    limit 500;
    return;
  end if;

  if entity_type_arg = 'theme' then
    return query
    with expanded as (
      select
        theme_entities.theme_key::text as key_value,
        theme_entities.display_name::text as display_value,
        theme_daily_views.date_key::text as date_value,
        lower(coalesce(view_item ->> 'account_name', view_item ->> 'author_name', view_item ->> 'username', '')) as author_name
      from public.theme_daily_views
      join public.theme_entities on theme_entities.id = theme_daily_views.theme_id
      cross join lateral jsonb_array_elements(coalesce(theme_daily_views.author_views_json, '[]'::jsonb)) as view_item
    )
    select
      key_value,
      display_value,
      max(date_value)::text,
      count(*)::integer,
      count(distinct author_name)::integer
    from expanded
    where author_name <> ''
      and (
        public.is_current_user_admin()
        or author_name in (
          select lower(x_accounts.username::text)
          from public.user_subscriptions
          join public.x_accounts on x_accounts.id = user_subscriptions.account_id
          where user_subscriptions.user_id = auth.uid()
        )
      )
    group by key_value, display_value
    order by max(date_value) desc, count(*) desc
    limit 500;
    return;
  end if;

  raise exception 'Unknown entity type.';
end;
$$;

grant execute on function public.list_my_entities(text) to authenticated;
