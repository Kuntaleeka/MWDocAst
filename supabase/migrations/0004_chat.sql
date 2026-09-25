-- Chat history, plus the per-answer records used by the debug and observability views.

create table public.conversations (
    id            uuid primary key default gen_random_uuid(),
    workspace_id  uuid not null references public.workspaces(id) on delete cascade,
    user_id       uuid not null references auth.users(id) on delete cascade,
    title         text not null,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);
create index conversations_workspace_idx on public.conversations (workspace_id, updated_at desc);

create table public.messages (
    id               uuid primary key default gen_random_uuid(),
    conversation_id  uuid not null references public.conversations(id) on delete cascade,
    workspace_id     uuid not null references public.workspaces(id) on delete cascade,
    role             text not null check (role in ('user', 'assistant')),
    content          text not null default '',
    -- The user's question is stored 'done' before the LLM is called; the assistant reply starts
    -- 'pending' and ends 'done' or 'failed', so a slow or failed LLM call never loses the question.
    status           text not null default 'done' check (status in ('pending', 'done', 'failed')),
    error            text,
    citations        jsonb not null default '[]',
    created_at       timestamptz not null default now()
);
create index messages_conversation_idx on public.messages (conversation_id, created_at);

-- What retrieval returned for each answer: proves which workspace and chunks an answer drew on.
create table public.retrieval_events (
    id            uuid primary key default gen_random_uuid(),
    message_id    uuid not null references public.messages(id) on delete cascade,
    workspace_id  uuid not null references public.workspaces(id) on delete cascade,
    query         text not null,
    hits          jsonb not null,             -- [{chunk_id, document_id, filename, section, similarity, used}]
    hit           boolean not null,           -- anything above the relevance floor?
    latency_ms    integer not null,
    created_at    timestamptz not null default now()
);
create index retrieval_events_message_idx on public.retrieval_events (message_id);

create table public.llm_requests (
    id                 uuid primary key default gen_random_uuid(),
    message_id         uuid references public.messages(id) on delete cascade,
    workspace_id       uuid not null references public.workspaces(id) on delete cascade,
    model              text not null,
    prompt_tokens      integer,
    completion_tokens  integer,
    latency_ms         integer not null,
    error              text,
    created_at         timestamptz not null default now()
);
create index llm_requests_workspace_idx on public.llm_requests (workspace_id, created_at desc);

alter table public.conversations    enable row level security;
alter table public.messages         enable row level security;
alter table public.retrieval_events enable row level security;
alter table public.llm_requests     enable row level security;
revoke all on public.conversations, public.messages, public.retrieval_events, public.llm_requests
    from anon, authenticated;
