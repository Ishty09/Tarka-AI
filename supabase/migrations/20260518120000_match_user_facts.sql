-- match_user_facts: pgvector top-K retrieval used by apps/workers
-- services/memory.py to assemble the §7.3 <user_facts> block on every
-- chat turn.
--
-- Additive only (CLAUDE.md §1.13 — no dropped or renamed objects). Uses
-- the hnsw cosine index already on user_facts.embedding (§6.2).
--
-- Filters at the function:
--   - user_id match (we accept it as a param so service-role callers
--     don't bypass user scoping)
--   - is_active = true (superseded facts are excluded from retrieval)
--   - embedding is not null (newly inserted facts that haven't been
--     embedded yet are silently skipped — the background embed pass
--     catches them within the same chat turn)
--   - similarity >= p_min_similarity (cuts noise; default 0.3)

create or replace function match_user_facts(
  p_user_id uuid,
  p_query_embedding vector(1536),
  p_match_count int default 10,
  p_min_similarity float default 0.3
)
returns table (
  id bigint,
  fact text,
  category text,
  confidence numeric,
  similarity float,
  created_at timestamptz
)
language sql
stable
as $$
  select
    uf.id,
    uf.fact,
    uf.category,
    uf.confidence,
    1 - (uf.embedding <=> p_query_embedding) as similarity,
    uf.created_at
  from user_facts uf
  where uf.user_id = p_user_id
    and uf.is_active = true
    and uf.embedding is not null
    and 1 - (uf.embedding <=> p_query_embedding) >= p_min_similarity
  order by uf.embedding <=> p_query_embedding
  limit p_match_count;
$$;

-- Service-role and the authenticated role both need to call this. Anon
-- callers do not — the function is internal to workers.
grant execute on function match_user_facts(uuid, vector(1536), int, float)
  to service_role, authenticated;
