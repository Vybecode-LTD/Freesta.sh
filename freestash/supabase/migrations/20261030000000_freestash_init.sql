-- Freestash: team schema (teams, collections, license ledger) with row-level security.
-- Mirrors src/freestash/store.py column for column. Apply with `supabase db push` or paste into the SQL editor.
--
-- Access model
--   * The FastAPI service connects with a server-side connection string and enforces team scoping
--     itself (it bypasses RLS). These policies are defense in depth for anything that talks to
--     Supabase directly: supabase-js in the browser, the SQL editor with a user JWT, future tools.
--   * The ledger is an audit trail: members can add and read, only team admins can delete, and
--     nobody updates rows in place.

create extension if not exists pgcrypto;

-- ------------------------------------------------------------------ tables
create table if not exists public.teams (
  id          uuid primary key default gen_random_uuid(),
  name        text not null check (char_length(name) between 1 and 200),
  created_at  timestamptz not null default now()
);

create table if not exists public.team_members (
  team_id  uuid not null references public.teams (id) on delete cascade,
  user_id  uuid not null references auth.users (id) on delete cascade,
  role     text not null default 'member' check (role in ('owner', 'admin', 'member')),
  primary key (team_id, user_id)
);
create index if not exists team_members_user_idx on public.team_members (user_id);

create table if not exists public.collections (
  id           uuid primary key default gen_random_uuid(),
  team_id      uuid references public.teams (id) on delete cascade,
  created_by   uuid references auth.users (id) on delete set null,
  name         text not null check (char_length(name) between 1 and 200),
  description  text,
  use_case     text not null default 'demo' check (use_case in ('reference', 'demo', 'client', 'bundled', 'merch')),
  created_at   timestamptz not null default now()
);
create index if not exists collections_team_idx on public.collections (team_id);

create table if not exists public.collection_items (
  id             uuid primary key default gen_random_uuid(),
  collection_id  uuid not null references public.collections (id) on delete cascade,
  asset_uid      text not null,
  asset          jsonb not null,
  verdict        jsonb not null,
  note           text,
  added_by       uuid references auth.users (id) on delete set null,
  added_at       timestamptz not null default now(),
  unique (collection_id, asset_uid)
);
create index if not exists collection_items_collection_idx on public.collection_items (collection_id);

create table if not exists public.ledger_entries (
  id             uuid primary key default gen_random_uuid(),
  team_id        uuid references public.teams (id) on delete cascade,
  created_by     uuid references auth.users (id) on delete set null,
  asset_uid      text not null,
  provider       text not null,
  title          text not null,
  creator        text,
  landing_url    text,
  file_url       text,
  license_id     text not null,
  license_label  text not null,
  license_url    text,
  license_raw    text,
  trust          text not null check (trust in ('institution', 'government', 'curated', 'community', 'uploader', 'unknown')),
  use_case       text not null check (use_case in ('reference', 'demo', 'client', 'bundled', 'merch')),
  tier           text not null check (tier in ('green', 'yellow', 'red')),
  attribution    text,
  project        text,
  sha256         text,
  local_path     text,
  bytes          integer,
  retrieved_at   timestamptz not null default now(),
  snapshot       jsonb not null default '{}'::jsonb
);
create index if not exists ledger_team_idx on public.ledger_entries (team_id, retrieved_at desc);
create index if not exists ledger_project_idx on public.ledger_entries (team_id, project);
create index if not exists ledger_asset_idx on public.ledger_entries (asset_uid);

-- ------------------------------------------------------------------ helpers
create or replace function public.is_team_member(t uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.team_members m where m.team_id = t and m.user_id = (select auth.uid()));
$$;

create or replace function public.is_team_admin(t uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.team_members m
                 where m.team_id = t and m.user_id = (select auth.uid()) and m.role in ('owner', 'admin'));
$$;

-- Create a team and make the caller its owner in one step.
create or replace function public.create_team(team_name text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare tid uuid;
begin
  if (select auth.uid()) is null then raise exception 'not authenticated'; end if;
  insert into public.teams (name) values (team_name) returning id into tid;
  insert into public.team_members (team_id, user_id, role) values (tid, (select auth.uid()), 'owner');
  return tid;
end $$;

revoke execute on function public.is_team_member(uuid), public.is_team_admin(uuid), public.create_team(text) from public, anon;
grant execute on function public.is_team_member(uuid), public.is_team_admin(uuid), public.create_team(text) to authenticated;

-- ------------------------------------------------------------------ RLS
alter table public.teams enable row level security;
alter table public.team_members enable row level security;
alter table public.collections enable row level security;
alter table public.collection_items enable row level security;
alter table public.ledger_entries enable row level security;

-- teams: members read; admins rename/delete; creation goes through create_team()
create policy teams_select on public.teams for select to authenticated using (public.is_team_member(id));
create policy teams_update on public.teams for update to authenticated using (public.is_team_admin(id)) with check (public.is_team_admin(id));
create policy teams_delete on public.teams for delete to authenticated using (public.is_team_admin(id));

-- team_members: members see the roster; admins manage it
create policy members_select on public.team_members for select to authenticated using (public.is_team_member(team_id));
create policy members_insert on public.team_members for insert to authenticated with check (public.is_team_admin(team_id));
create policy members_update on public.team_members for update to authenticated using (public.is_team_admin(team_id)) with check (public.is_team_admin(team_id));
create policy members_delete on public.team_members for delete to authenticated
  using (public.is_team_admin(team_id) or user_id = (select auth.uid()));  -- you can always leave

-- collections: any member can work with the team's collections
create policy collections_select on public.collections for select to authenticated using (public.is_team_member(team_id));
create policy collections_insert on public.collections for insert to authenticated
  with check (public.is_team_member(team_id) and created_by = (select auth.uid()));
create policy collections_update on public.collections for update to authenticated using (public.is_team_member(team_id)) with check (public.is_team_member(team_id));
create policy collections_delete on public.collections for delete to authenticated using (public.is_team_member(team_id));

-- collection_items: inherit from the parent collection
create policy items_select on public.collection_items for select to authenticated
  using (exists (select 1 from public.collections c where c.id = collection_id and public.is_team_member(c.team_id)));
create policy items_insert on public.collection_items for insert to authenticated
  with check (added_by = (select auth.uid()) and exists (select 1 from public.collections c where c.id = collection_id and public.is_team_member(c.team_id)));
create policy items_update on public.collection_items for update to authenticated
  using (exists (select 1 from public.collections c where c.id = collection_id and public.is_team_member(c.team_id)));
create policy items_delete on public.collection_items for delete to authenticated
  using (exists (select 1 from public.collections c where c.id = collection_id and public.is_team_member(c.team_id)));

-- ledger: append-only audit trail
create policy ledger_select on public.ledger_entries for select to authenticated using (public.is_team_member(team_id));
create policy ledger_insert on public.ledger_entries for insert to authenticated
  with check (public.is_team_member(team_id) and created_by = (select auth.uid()));
create policy ledger_delete on public.ledger_entries for delete to authenticated using (public.is_team_admin(team_id));
-- (no update policy on purpose)
