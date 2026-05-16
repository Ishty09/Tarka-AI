-- Extensions required by the schema.
-- pgvector: vector(1536) embeddings on user_facts + hnsw index (§6.2).
-- pgcrypto: gen_random_uuid() defaults across multiple tables (§6.1, §6.3, §6.4, §6.5, §6.6).

create extension if not exists vector;
create extension if not exists pgcrypto;
