-- §6.3 roast feed: shared posts derived from chat messages + per-user votes.

create table roast_feed_posts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  conversation_id uuid not null references conversations(id) on delete cascade,
  message_id bigint not null references messages(id) on delete cascade,
  caption text,
  upvotes integer not null default 0,
  downvotes integer not null default 0,
  is_safe boolean not null default true,
  moderation_status text not null default 'pending' check (moderation_status in ('pending','approved','rejected','flagged')),
  visibility text not null default 'public' check (visibility in ('public','unlisted','removed')),
  share_count integer not null default 0,
  created_at timestamptz not null default now()
);
create index idx_roast_feed_recent on roast_feed_posts(created_at desc)
  where visibility = 'public' and moderation_status = 'approved';
create index idx_roast_feed_hot on roast_feed_posts((upvotes - downvotes) desc)
  where visibility = 'public' and moderation_status = 'approved';

alter table roast_feed_posts enable row level security;
create policy roast_feed_public_read on roast_feed_posts for select using (
  visibility = 'public' and moderation_status = 'approved'
);
create policy roast_feed_owner on roast_feed_posts for all using (user_id = auth.uid());


create table roast_feed_votes (
  post_id uuid not null references roast_feed_posts(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  vote smallint not null check (vote in (-1, 1)),
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

alter table roast_feed_votes enable row level security;
create policy roast_feed_votes_self on roast_feed_votes for all using (user_id = auth.uid());
