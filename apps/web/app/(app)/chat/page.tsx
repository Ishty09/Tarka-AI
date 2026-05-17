import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { archiveConversation, unarchiveConversation } from "./actions";

// Conversations list — the chat home. Pulls the user's conversations and
// their persona names via an embedded foreign-key select. RLS scopes the
// read to the signed-in user (§6.7). ?show=archived flips the filter.

interface PageProps {
  searchParams: Promise<{ show?: string }>;
}

export default async function ChatListPage({ searchParams }: PageProps) {
  const { show } = await searchParams;
  const archivedView = show === "archived";

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: conversations } = await supabase
    .from("conversations")
    .select("id, title, mode, updated_at, archived, persona:personas(slug, name)")
    .eq("user_id", user.id)
    .eq("archived", archivedView)
    .order("updated_at", { ascending: false })
    .limit(50);

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          {archivedView ? "Archived conversations" : "Your conversations"}
        </h1>
        <div className="flex items-center gap-2">
          <Link
            href={archivedView ? "/chat" : "/chat?show=archived"}
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-2 text-sm font-medium shadow-sm hover:bg-accent"
          >
            {archivedView ? "Active" : "Archived"}
          </Link>
          <Link
            href="/personas"
            className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            Start new
          </Link>
        </div>
      </div>

      {(!conversations || conversations.length === 0) ? (
        <p className="mt-8 text-sm text-muted-foreground">
          {archivedView
            ? "Nothing archived yet."
            : "No conversations yet. Pick a persona to start a fight."}
        </p>
      ) : (
        <ul className="mt-6 flex flex-col gap-2">
          {conversations.map((c) => {
            const persona = Array.isArray(c.persona) ? c.persona[0] : c.persona;
            return (
              <li
                key={c.id}
                className="flex items-center gap-3 rounded-md border border-input bg-background px-4 py-3 text-sm shadow-sm"
              >
                <Link href={`/chat/${c.id}`} className="flex flex-1 items-center justify-between hover:opacity-90">
                  <div className="flex flex-col">
                    <span className="font-medium">{c.title ?? "Untitled"}</span>
                    <span className="text-xs text-muted-foreground">
                      {persona?.name ?? "—"} · {c.mode}
                    </span>
                  </div>
                  <time className="text-xs text-muted-foreground">
                    {new Date(c.updated_at).toLocaleDateString()}
                  </time>
                </Link>
                <form
                  action={archivedView ? unarchiveConversation : archiveConversation}
                  className="shrink-0"
                >
                  <input type="hidden" name="id" value={c.id} />
                  <button
                    type="submit"
                    className="rounded-md border border-input bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                  >
                    {archivedView ? "Unarchive" : "Archive"}
                  </button>
                </form>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
