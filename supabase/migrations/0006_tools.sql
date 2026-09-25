-- Tool calling: the side effect (tasks) and an audit log of every call the model asked for,
-- including the ones we refused.

create table public.tasks (
    id                 uuid primary key default gen_random_uuid(),
    workspace_id       uuid not null references public.workspaces(id) on delete cascade,
    title              text not null check (char_length(title) between 1 and 200),
    notes              text check (char_length(notes) <= 1000),
    due_date           date,
    status             text not null default 'open' check (status in ('open', 'done')),
    created_by         uuid references auth.users(id) on delete set null,
    source_message_id  uuid references public.messages(id) on delete set null,
    created_at         timestamptz not null default now()
);
create index tasks_workspace_idx on public.tasks (workspace_id, created_at desc);

create table public.tool_calls (
    id            uuid primary key default gen_random_uuid(),
    workspace_id  uuid not null references public.workspaces(id) on delete cascade,
    message_id    uuid references public.messages(id) on delete cascade,
    name          text not null,               -- as requested by the model, even if unknown
    args          jsonb not null,
    status        text not null check (status in ('ok', 'rejected', 'error')),
    result        jsonb,
    error         text,
    latency_ms    integer not null,
    created_at    timestamptz not null default clock_timestamp()
);
create index tool_calls_workspace_idx on public.tool_calls (workspace_id, created_at desc);
create index tool_calls_message_idx on public.tool_calls (message_id);

alter table public.tasks      enable row level security;
alter table public.tool_calls enable row level security;
revoke all on public.tasks, public.tool_calls from anon, authenticated;
