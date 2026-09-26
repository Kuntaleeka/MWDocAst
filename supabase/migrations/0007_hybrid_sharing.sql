-- Stretch goals: hybrid (keyword + vector) retrieval, opt-in document sharing, answer latency.

-- Load pgvector in this session first. Until its library is loaded, hnsw.iterative_scan is an
-- unknown placeholder setting, and `create function ... set hnsw.iterative_scan` is refused with
-- "permission denied to set parameter".
select '[1]'::extensions.vector;

-- Opt-in sharing: a document stays in its own workspace; a row here makes it readable (never
-- writable) from one other workspace. No row = default isolation.
create table public.document_shares (
    document_id          uuid not null references public.documents(id) on delete cascade,
    target_workspace_id  uuid not null references public.workspaces(id) on delete cascade,
    shared_by            uuid references auth.users(id) on delete set null,
    created_at           timestamptz not null default now(),
    primary key (document_id, target_workspace_id)
);
create index document_shares_target_idx on public.document_shares (target_workspace_id);
alter table public.document_shares enable row level security;
revoke all on public.document_shares from anon, authenticated;

-- End-to-end answer latency for observability (created_at → completed_at).
alter table public.messages add column completed_at timestamptz;

-- Hybrid search, scoped to what p_workspace_id may read: its own chunks plus chunks of documents
-- explicitly shared into it. That visibility filter is applied inside BOTH candidate queries
-- (vector and keyword), so neither ranking ever sees another workspace's rows, and again in the
-- final join. Candidates are fused with Reciprocal Rank Fusion: score = Σ 1 / (60 + rank).
-- p_mode = 'vector' skips the keyword side (used to measure what hybrid adds).
create or replace function public.search_chunks(
    p_workspace_id uuid,
    p_embedding    extensions.vector(768),
    p_query        text,
    p_k            integer default 8,
    p_mode         text default 'hybrid'
)
returns table (
    chunk_id             uuid,
    document_id          uuid,
    filename             text,
    section              text,
    content              text,
    similarity           double precision,
    vector_rank          integer,
    keyword_rank         integer,
    score                double precision,
    source_workspace_id  uuid
)
language sql
stable
set search_path = public, extensions
set hnsw.iterative_scan = 'relaxed_order'
as $$
    with shared as (
        select coalesce(array_agg(s.document_id), '{}') as ids
        from document_shares s where s.target_workspace_id = p_workspace_id
    ),
    vec as materialized (
        select c.id, c.embedding <=> p_embedding as distance
        from chunks c
        where c.workspace_id = p_workspace_id or c.document_id = any ((select ids from shared)::uuid[])
        order by c.embedding <=> p_embedding
        limit 30
    ),
    vec_ranked as (
        select id, row_number() over (order by distance) as r from vec
    ),
    -- OR the query's lexemes together: natural questions rarely contain every term of a chunk.
    q as (
        select nullif(replace(plainto_tsquery('english', coalesce(p_query, ''))::text, ' & ', ' | '), '')::tsquery as tsq
        where p_mode = 'hybrid'
    ),
    kw as (
        select c.id, row_number() over (order by ts_rank_cd(c.tsv, q.tsq) desc) as r
        from chunks c, q
        where q.tsq is not null
          and (c.workspace_id = p_workspace_id or c.document_id = any ((select ids from shared)::uuid[]))
          and c.tsv @@ q.tsq
        order by ts_rank_cd(c.tsv, q.tsq) desc
        limit 30
    ),
    fused as (
        select coalesce(v.id, k.id) as id, v.r as vr, k.r as kr,
               coalesce(1.0 / (60 + v.r), 0) + coalesce(1.0 / (60 + k.r), 0) as score
        from vec_ranked v full outer join kw k on k.id = v.id
    )
    select c.id, c.document_id, d.filename, c.section, c.content,
           1 - (c.embedding <=> p_embedding), f.vr::integer, f.kr::integer, f.score::double precision,
           d.workspace_id
    from fused f
    join chunks c on c.id = f.id
    join documents d on d.id = c.document_id
    where d.status = 'ready'
      and (d.workspace_id = p_workspace_id or d.id = any ((select ids from shared)::uuid[]))
    order by f.score desc, 1 - (c.embedding <=> p_embedding) desc
    limit least(greatest(p_k, 1), 50);
$$;

revoke execute on function public.search_chunks(uuid, extensions.vector, text, integer, text)
    from public, anon, authenticated;

-- match_chunks (0003) is superseded by search_chunks; it is dropped in a later migration once the
-- deployed code no longer calls it (local and production share this database).
