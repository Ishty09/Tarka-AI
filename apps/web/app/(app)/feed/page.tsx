import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { castVote } from "./actions";

// Public Roast Feed (§9.2.5). RLS roast_feed_public_read scopes the
// read to visibility='public' AND moderation_status='approved' (§6.7), so
// the SELECT here doesn't need to repeat those filters — but we add them
// explicitly anyway for clarity and so a misconfigured RLS policy doesn't
// silently leak.
//
// Two sort modes via ?sort=hot|recent. "Hot" is (upvotes - downvotes)
// desc with recency as a tiebreaker — the post indexes on
// (upvotes - downvotes) desc already, so this is cheap.

interface PageProps {
  searchParams: Promise<{ sort?: string }>;
}

type FeedRow = {
  id: string;
  user_id: string;
  caption: string | null;
  upvotes: number;
  downvotes: number;
  share_count: number;
  created_at: string;
  author: { username: string | null; display_name: string | null } | { username: string | null; display_name: string | null }[] | null;
  message: {
    content: string;
    redacted_content: string | null;
    metadata: Record<string, unknown> | null;
  } | { content: string; redacted_content: string | null; metadata: Record<string, unknown> | null }[] | null;
  my_vote: { vote: number } | { vote: number }[] | null;
};

function unwrap<T>(v: T | T[] | null): T | null {
  if (!v) return null;
  return Array.isArray(v) ? v[0] ?? null : v;
}

export default async function FeedPage({ searchParams }: PageProps) {
  const { sort } = await searchParams;
  const hot = sort === "hot";

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Embed user's vote via filtered join so the UI can highlight what they
  // picked. Filtering happens in the embed `roast_feed_votes!inner` won't
  // work for "left join with my vote only" — use !roast_feed_votes(...)
  // and filter inside.
  const baseSelect =
    "id, user_id, caption, upvotes, downvotes, share_count, created_at, "
    + "author:profiles!user_id(username, display_name), "
    + "message:messages!message_id(content, redacted_content, metadata), "
    + `my_vote:roast_feed_votes(vote)`;

  let query = supabase
    .from("roast_feed_posts")
    .select(baseSelect)
    .eq("visibility", "public")
    .eq("moderation_status", "approved")
    .limit(50);

  query = hot
    ? query.order("upvotes", { ascending: false }).order("created_at", { ascending: false })
    : query.order("created_at", { ascending: false });

  const { data: rawRows } = await query;
  const rows = (rawRows ?? []) as unknown as FeedRow[];

  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Roast feed</h1>
        <nav className="flex gap-2 text-sm">
          <Link
            href="/feed"
            className={`rounded-md border border-input px-3 py-1 ${!hot ? "bg-primary text-primary-foreground" : "bg-background hover:bg-accent"}`}
          >
            Recent
          </Link>
          <Link
            href="/feed?sort=hot"
            className={`rounded-md border border-input px-3 py-1 ${hot ? "bg-primary text-primary-foreground" : "bg-background hover:bg-accent"}`}
          >
            Hot
          </Link>
        </nav>
      </div>

      {rows.length === 0 ? (
        <p className="mt-10 text-sm text-muted-foreground">
          Nothing in the feed yet. Share your first roast from a chat.
        </p>
      ) : (
        <ul className="mt-6 flex flex-col gap-4">
          {rows.map((row) => {
            const author = unwrap(row.author);
            const message = unwrap(row.message);
            const myVote = unwrap(row.my_vote);
            const score = (row.upvotes ?? 0) - (row.downvotes ?? 0);
            const content = message?.redacted_content ?? message?.content ?? "";
            const personaName = (() => {
              const meta = message?.metadata as Record<string, unknown> | undefined;
              const persona = meta && typeof meta === "object" ? meta["persona_name"] : null;
              return typeof persona === "string" ? persona : null;
            })();
            return (
              <li
                key={row.id}
                className="flex gap-3 rounded-md border border-input bg-background p-4 shadow-sm"
              >
                <VoteColumn
                  postId={row.id}
                  score={score}
                  myVote={myVote?.vote ?? 0}
                />
                <div className="flex-1">
                  <header className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      {personaName && <span className="font-medium text-foreground">{personaName}</span>}
                      {personaName && " · "}
                      @{author?.username ?? "anon"}
                    </span>
                    <time>{new Date(row.created_at).toLocaleDateString()}</time>
                  </header>
                  {row.caption && (
                    <p className="mt-2 text-xs italic text-muted-foreground">{row.caption}</p>
                  )}
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
                  <footer className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{row.share_count ?? 0} shares</span>
                  </footer>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

function VoteColumn({
  postId,
  score,
  myVote,
}: {
  postId: string;
  score: number;
  myVote: number;
}) {
  return (
    <div className="flex shrink-0 flex-col items-center gap-1 pt-1">
      <form action={castVote}>
        <input type="hidden" name="post_id" value={postId} />
        <input type="hidden" name="vote" value="1" />
        <button
          type="submit"
          aria-label="Upvote"
          className={`flex size-7 items-center justify-center rounded-md border border-input text-sm hover:bg-accent ${myVote === 1 ? "border-emerald-500 bg-emerald-500/10 text-emerald-700" : "bg-background"}`}
        >
          ▲
        </button>
      </form>
      <span className="font-mono text-xs">{score}</span>
      <form action={castVote}>
        <input type="hidden" name="post_id" value={postId} />
        <input type="hidden" name="vote" value="-1" />
        <button
          type="submit"
          aria-label="Downvote"
          className={`flex size-7 items-center justify-center rounded-md border border-input text-sm hover:bg-accent ${myVote === -1 ? "border-red-500 bg-red-500/10 text-red-700" : "bg-background"}`}
        >
          ▼
        </button>
      </form>
    </div>
  );
}
