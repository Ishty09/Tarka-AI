-- Sidebar conversation list — replace the layout's two-query
-- (conversations + IN(...) messages scan) with one RPC. Without this,
-- the sidebar pulls EVERY user message across the last 80 conversations
-- on every navigation just to derive a fallback title. With this, one
-- index hit per conversation, no full-message scan.

create or replace function get_sidebar_conversations(
  p_user_id uuid,
  p_limit int default 30
)
returns table (
  id uuid,
  title text,
  mode text,
  updated_at timestamptz,
  archived boolean,
  persona_name text,
  first_user_message text
)
language sql
stable
security invoker  -- RLS still applies — caller's auth.uid() must match user_id
set search_path = public, pg_temp
as $$
  select
    c.id,
    c.title,
    c.mode,
    c.updated_at,
    c.archived,
    p.name as persona_name,
    substring(
      (select m.content from messages m
       where m.conversation_id = c.id and m.role = 'user'
       order by m.id asc limit 1)
      for 200
    ) as first_user_message
  from conversations c
  left join personas p on p.id = c.persona_id
  where c.user_id = p_user_id
    and c.archived = false
  order by c.updated_at desc
  limit p_limit;
$$;

grant execute on function get_sidebar_conversations(uuid, int) to anon, authenticated, service_role;

-- Speeds up the per-conversation first-message subquery above.
create index if not exists idx_messages_conv_role_id
  on messages(conversation_id, role, id);
