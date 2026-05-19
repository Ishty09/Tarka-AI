import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";

// Shared "Recent runs" panel used by /tools/* pages. Reads the
// signed-in user's conversations of a given mode and shows the last
// few — clickable into /chat/[id] for the persisted result.

type ConversationRow = {
  id: string;
  title: string | null;
  updated_at: string;
  metadata: Record<string, unknown> | null;
  message: { content: string }[] | null;
};

interface Props {
  mode: string;
  /** Optional `metadata.tool` filter for modes like 'custom' that host
   *  multiple tools. Empty means no filter. */
  toolKey?: string;
  /** Max entries to render. */
  limit?: number;
}

export async function RecentRuns({ mode, toolKey, limit = 5 }: Props) {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;

  // Pull the first user message of each conversation as a preview. The
  // foreign-key embed reads the oldest message; we ask for one and
  // accept that quirky mode='custom' tools share a conversation table
  // with everything else.
  const { data: rowsData } = await supabase
    .from("conversations")
    .select(
      "id, title, updated_at, metadata, message:messages(content)",
    )
    .eq("user_id", user.id)
    .eq("mode", mode)
    .eq("archived", false)
    .order("updated_at", { ascending: false })
    .limit(limit * 2); // over-fetch to filter client-side by toolKey
  const allRows = (rowsData ?? []) as unknown as ConversationRow[];
  const rows = toolKey
    ? allRows
        .filter((r) => {
          const meta = r.metadata ?? {};
          return typeof meta === "object" && (meta as Record<string, unknown>).tool === toolKey;
        })
        .slice(0, limit)
    : allRows.slice(0, limit);

  if (rows.length === 0) return null;

  return (
    <section className="mt-10">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Recent runs
      </h2>
      <ul className="mt-3 flex flex-col gap-2">
        {rows.map((row) => {
          const firstMsg = Array.isArray(row.message) ? row.message[0] : null;
          const preview = firstMsg?.content?.slice(0, 140) ?? "—";
          return (
            <li key={row.id}>
              <Link
                href={`/chat/${row.id}`}
                className="flex items-center justify-between gap-3 rounded-md border border-input bg-background px-4 py-3 text-sm shadow-sm hover:bg-accent"
              >
                <div className="flex flex-col">
                  <span className="line-clamp-1 text-xs text-muted-foreground">
                    {preview}
                  </span>
                  <time className="mt-1 text-[10px] text-muted-foreground">
                    {new Date(row.updated_at).toLocaleString()}
                  </time>
                </div>
                <span className="text-xs text-muted-foreground">→</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
