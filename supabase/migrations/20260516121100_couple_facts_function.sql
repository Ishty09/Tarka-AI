-- §6.7 get_couple_facts: triple-consent gated cross-fact retrieval.
--
-- Triple gate (CLAUDE.md §9.3.1):
--   1. couple link is active
--   2. both partners consented to the link (consent_a + consent_b)
--   3. both partners consented to cross-fact retrieval (cross_fact_consent_a + cross_fact_consent_b)
--
-- Every call is logged to audit_log so the partner can later see who pulled what.
-- security definer is required to bypass user_facts RLS for the other partner's
-- rows; the consent checks above are the access gate.

create or replace function get_couple_facts(p_couple_link_id uuid)
returns table(
  fact_id bigint,
  owner_id uuid,
  fact text,
  category text,
  confidence numeric,
  created_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  link record;
begin
  select * into link from couple_links where id = p_couple_link_id;

  if link.status != 'active' then raise exception 'Couple link not active'; end if;
  if not (link.consent_a and link.consent_b) then raise exception 'Couple consent missing'; end if;
  if not (link.cross_fact_consent_a and link.cross_fact_consent_b) then
    raise exception 'Cross-fact consent missing';
  end if;
  if auth.uid() not in (link.user_a, link.user_b) then raise exception 'Not authorized'; end if;

  insert into audit_log (actor_user_id, action, entity_type, entity_id, metadata)
  values (
    auth.uid(),
    'cross_fact_retrieval',
    'couple_link',
    p_couple_link_id::text,
    jsonb_build_object(
      'partner_id', case when auth.uid() = link.user_a then link.user_b else link.user_a end
    )
  );

  return query
    select uf.id, uf.user_id, uf.fact, uf.category, uf.confidence, uf.created_at
    from user_facts uf
    where uf.user_id in (link.user_a, link.user_b)
      and uf.is_active = true
    order by uf.created_at desc;
end;
$$;

-- Only authenticated users may invoke; anon role gets nothing.
revoke all on function get_couple_facts(uuid) from public;
grant execute on function get_couple_facts(uuid) to authenticated;
