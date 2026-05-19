import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { fetchPendingFeedPosts, fetchPendingPersonas } from "@/lib/admin";
import { PersonaRow } from "./PersonaRow";
import { FeedPostRow } from "./FeedPostRow";

// Two queues stacked: pending personas first, then pending feed posts. Each
// row is its own form so simultaneous moderate clicks don't collide.

export default async function ModerationPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const [personas, posts] = await Promise.all([
    fetchPendingPersonas(user.id),
    fetchPendingFeedPosts(user.id),
  ]);

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <header>
          <h2 className="text-lg font-semibold tracking-tight">Personas</h2>
          <p className="text-xs text-muted-foreground">
            User-submitted personas awaiting review. Approval makes them visible
            in the marketplace; rejection hides them but keeps the row for
            audit.
          </p>
        </header>
        {!personas.ok && (
          <p className="text-xs text-destructive">
            Couldn&apos;t load: {personas.status} {personas.error}
          </p>
        )}
        {personas.ok && personas.data.personas.length === 0 && (
          <p className="text-sm text-muted-foreground">Queue is empty.</p>
        )}
        {personas.ok &&
          personas.data.personas.map((p) => <PersonaRow key={p.id} persona={p} />)}
      </section>

      <section className="flex flex-col gap-3">
        <header>
          <h2 className="text-lg font-semibold tracking-tight">Feed posts</h2>
          <p className="text-xs text-muted-foreground">
            Posts queued for the public Roast Feed, plus any later flagged for
            re-review.
          </p>
        </header>
        {!posts.ok && (
          <p className="text-xs text-destructive">
            Couldn&apos;t load: {posts.status} {posts.error}
          </p>
        )}
        {posts.ok && posts.data.posts.length === 0 && (
          <p className="text-sm text-muted-foreground">Queue is empty.</p>
        )}
        {posts.ok && posts.data.posts.map((p) => <FeedPostRow key={p.id} post={p} />)}
      </section>
    </div>
  );
}
