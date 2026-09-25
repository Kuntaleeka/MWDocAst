-- Workspace-scoped vector search. The workspace filter is part of the vector query itself,
-- so rows from other workspaces are never candidates, not merely filtered from the output.
--
-- hnsw.iterative_scan: with a WHERE clause, a plain HNSW scan fetches ef_search nearest
-- neighbours from the WHOLE table and then filters, which can return fewer than k rows (or none)
-- when other workspaces dominate the neighbourhood. Iterative scan keeps walking the graph until
-- k rows pass the filter. relaxed_order can emit slightly out-of-order rows, so the outer query
-- re-sorts by distance.

create or replace function public.match_chunks(
    p_workspace_id uuid,
    p_embedding    extensions.vector(768),
    p_k            integer default 8
)
returns table (
    chunk_id     uuid,
    document_id  uuid,
    filename     text,
    section      text,
    content      text,
    similarity   double precision
)
language sql
stable
set search_path = public, extensions
set hnsw.iterative_scan = 'relaxed_order'
as $$
    with nearest as materialized (
        select c.id, c.document_id, c.section, c.content,
               c.embedding <=> p_embedding as distance
        from chunks c
        where c.workspace_id = p_workspace_id
        order by c.embedding <=> p_embedding
        limit least(greatest(p_k, 1), 50)
    )
    select n.id, n.document_id, d.filename, n.section, n.content, 1 - n.distance
    from nearest n
    join documents d on d.id = n.document_id and d.workspace_id = p_workspace_id
    where d.status = 'ready'
    order by n.distance;
$$;

-- Postgres grants EXECUTE on new functions to PUBLIC, and Supabase exposes public functions over
-- REST. Only the API's server role may call this.
revoke execute on function public.match_chunks(uuid, extensions.vector, integer)
    from public, anon, authenticated;
