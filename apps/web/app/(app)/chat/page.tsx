import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

// Conversations list — the chat home. Pulls the user's most recent
// (non-archived) conversations and their persona names via an embedded
// foreign-key select. RLS scopes the read to the signed-in user (§6.7).

export default async function ChatListPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: conversations } = await supabase
    .from("conversations")
    .select("id, title, mode, updated_at, persona:personas(slug, name)")
    .eq("user_id", user.id)
    .eq("archived", false)
    .order("updated_at", { ascending: false })
    .limit(50);

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Your conversations</h1>
        <Link
          href="/personas"
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          Start new
        </Link>
      </div>

      {(!conversations || conversations.length === 0) ? (
        <p className="mt-8 text-sm text-muted-foreground">
          No conversations yet. Pick a persona to start a fight.
        </p>
      ) : (
        <ul className="mt-6 flex flex-col gap-2">
          {conversations.map((c) => {
            const persona = Array.isArray(c.persona) ? c.persona[0] : c.persona;
            return (
              <li key={c.id}>
                <Link
                  href={`/chat/${c.id}`}
                  className="flex items-center justify-between rounded-md border border-input bg-background px-4 py-3 text-sm shadow-sm hover:bg-accent"
                >
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
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
