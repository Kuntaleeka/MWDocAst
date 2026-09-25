-- Workspaces and membership. Every tenant-scoped table added later carries a workspace_id
-- that references workspaces(id).

create table public.workspaces (
    id          uuid primary key default gen_random_uuid(),
    name        text not null check (char_length(name) between 1 and 80),
    created_by  uuid not null references auth.users(id) on delete cascade,
    created_at  timestamptz not null default now()
);

create table public.workspace_members (
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    user_id      uuid not null references auth.users(id) on delete cascade,
    role         text not null default 'owner' check (role in ('owner', 'member')),
    created_at   timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

create index workspace_members_user_idx on public.workspace_members(user_id);

-- The browser never queries tables directly: all reads/writes go through the Python API,
-- which connects as a privileged role and enforces membership itself. RLS with no policies
-- makes the Supabase REST API (anon/authenticated roles) deny everything as a second wall.
alter table public.workspaces        enable row level security;
alter table public.workspace_members enable row level security;
revoke all on public.workspaces, public.workspace_members from anon, authenticated;
