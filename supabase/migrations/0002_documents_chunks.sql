-- Documents and THE shared vector store. Every workspace's chunks live in one `chunks` table;
-- isolation is enforced by filtering workspace_id inside every query, never by separate tables.

create extension if not exists vector with schema extensions;

create table public.documents (
    id            uuid primary key default gen_random_uuid(),
    workspace_id  uuid not null references public.workspaces(id) on delete cascade,
    filename      text not null,
    content_hash  text not null,                -- sha256 of the raw bytes, computed server-side
    size_bytes    integer not null,
    storage_path  text not null,
    status        text not null default 'processing'
                  check (status in ('processing', 'ready', 'failed')),
    error         text,
    uploaded_by   uuid references auth.users(id) on delete set null,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (workspace_id, content_hash)         -- re-uploading the same file is a no-op
);

create table public.chunks (
    id            uuid primary key default gen_random_uuid(),
    workspace_id  uuid not null references public.workspaces(id) on delete cascade,
    document_id   uuid not null references public.documents(id) on delete cascade,
    chunk_index   integer not null,
    section       text,                         -- heading path or "p. N", used in citations
    content       text not null,
    embedding     extensions.vector(768) not null,
    tsv           tsvector generated always as
                  (to_tsvector('english', coalesce(section, '') || ' ' || content)) stored,
    created_at    timestamptz not null default now(),
    unique (document_id, chunk_index)
);

create index chunks_workspace_idx on public.chunks (workspace_id);
create index chunks_embedding_hnsw on public.chunks
    using hnsw (embedding extensions.vector_cosine_ops);
create index chunks_tsv_idx on public.chunks using gin (tsv);
create index documents_workspace_idx on public.documents (workspace_id, created_at desc);

alter table public.documents enable row level security;
alter table public.chunks    enable row level security;
revoke all on public.documents, public.chunks from anon, authenticated;

-- Private bucket for raw uploads. Objects are keyed "<workspace_id>/<uuid>/<filename>".
-- No storage policies: the browser can only write via short-lived signed upload URLs
-- that the API issues after checking membership.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('documents', 'documents', false, 10485760,
        array['application/pdf', 'text/plain', 'text/markdown', 'text/x-markdown'])
on conflict (id) do nothing;
