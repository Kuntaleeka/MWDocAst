-- search_chunks (0007) replaced match_chunks (0003); the deployed code no longer calls it.
drop function if exists public.match_chunks(uuid, extensions.vector, integer);
