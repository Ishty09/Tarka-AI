import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { createServerSupabase } from "@/lib/supabase/server";
import { env, serverEnv } from "@/lib/env";
import type { ChatTurn } from "@/app/(app)/chat/_components/useChatStream";
import { revokeLink } from "../actions";
import { CouplesChat } from "./CouplesChat";
import { CrossFactConsent } from "./CrossFactConsent";

// /couples/[linkId] (§9.3.1). Three rendered states:
//   - pending: copy-the-invite UI for the creator; "waiting" for the
//     accepter (shouldn't normally be reached by user_b since accept
//     redirects here once active).
//   - active: starts the shared conversation (idempotent worker call) and
//     hands off to CouplesChat for the actual chat surface.
//   - revoked / expired: archive copy.

interface PageProps {
  params: Promise<{ linkId: string }>;
}

type DetailRow = {
  id: string;
  user_a: string;
  user_b: string | null;
  status: string;
  consent_a: boolean;
  consent_b: boolean;
  cross_fact_consent_a: boolean;
  cross_fact_consent_b: boolean;
  created_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
  partner_a: { username: string | null; display_name: string | null } | { username: string | null; display_name: string | null }[] | null;
  partner_b: { username: string | null; display_name: string | null } | { username: string | null; display_name: string | null }[] | null;
};

function unwrap<T>(v: T | T[] | null): T | null {
  if (!v) return null;
  return Array.isArray(v) ? v[0] ?? null : v;
}

export default async function CoupleLinkDetailPage({ params }: PageProps) {
  const { linkId } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: rowData } = await supabase
    .from("couple_links")
    .select(
      "id, user_a, user_b, status, consent_a, consent_b, cross_fact_consent_a, cross_fact_consent_b, created_at, revoked_at, revoked_by, "
      + "partner_a:profiles!user_a(username, display_name), "
      + "partner_b:profiles!user_b(username, display_name)",
    )
    .eq("id", linkId)
    .maybeSingle();
  const link = rowData as DetailRow | null;
  if (!link) notFound();

  const youAreCreator = link.user_a === user.id;
  const otherProfile = unwrap(youAreCreator ? link.partner_b : link.partner_a);
  const partnerName = otherProfile?.display_name ?? otherProfile?.username ?? "your partner";

  if (link.status === "active") {
    // Start (or find) the shared conversation via workers. Server-side
    // fetch with the user's cookie session forwarded as bearer through
    // /api/couples/start would require a circular fetch — call workers
    // directly with the internal secret here.
    const cookieHeader = (await headers()).get("cookie") ?? "";
    void cookieHeader; // unused — kept for clarity if we route through web later
    let conversationId: string | null = null;
    let conversationError: string | null = null;
    if (!serverEnv.WORKERS_INTERNAL_SECRET) {
      conversationError = "Workers not configured.";
    } else {
      const upstream = await fetch(`${serverEnv.WORKERS_URL}/tools/couples/start`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
          "x-user-id": user.id,
        },
        body: JSON.stringify({ link_id: link.id }),
        cache: "no-store",
      });
      if (upstream.ok) {
        const body = (await upstream.json()) as { conversation_id: string };
        conversationId = body.conversation_id;
      } else {
        conversationError = `Couldn't open chat (${upstream.status}).`;
      }
    }

    if (!conversationId) {
      return (
        <main className="mx-auto w-full max-w-2xl p-6">
          <Link href="/couples" className="text-sm text-muted-foreground hover:underline">
            ← Couples
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            You + {partnerName}
          </h1>
          <p role="alert" className="mt-4 text-sm text-destructive">
            {conversationError ?? "Couldn't open chat."}
          </p>
        </main>
      );
    }

    const { data: messageRows } = await supabase
      .from("messages")
      .select("id, role, content, redacted_content, user_id, safety_verdict")
      .eq("conversation_id", conversationId)
      .in("role", ["user", "assistant"])
      .order("id", { ascending: true })
      .limit(100);
    const initialMessages: ChatTurn[] = (messageRows ?? []).map((m) => ({
      id: String(m.id),
      role: m.role as "user" | "assistant",
      content: m.redacted_content ?? m.content,
      persistedMessageId: m.id,
      ...(m.safety_verdict && m.safety_verdict !== "safe"
        ? { safetyVerdict: m.safety_verdict }
        : {}),
    }));

    void env; // touched to avoid unused-import in this branch

    const partners = {
      user_a: {
        id: link.user_a,
        name:
          unwrap(link.partner_a)?.display_name
          ?? unwrap(link.partner_a)?.username
          ?? "Partner A",
      },
      user_b: {
        id: link.user_b ?? "",
        name:
          unwrap(link.partner_b)?.display_name
          ?? unwrap(link.partner_b)?.username
          ?? "Partner B",
      },
    };

    const youAreA = link.user_a === user.id;
    const yourConsent = youAreA ? link.cross_fact_consent_a : link.cross_fact_consent_b;
    const partnerConsent = youAreA ? link.cross_fact_consent_b : link.cross_fact_consent_a;

    return (
      <div className="flex flex-col">
        <div className="scrollbar-none flex items-center gap-4 overflow-x-auto whitespace-nowrap border-b bg-gradient-to-r from-violet-500/10 to-fuchsia-500/10 px-4 py-2 text-sm md:flex-wrap md:whitespace-normal">
          <Link
            href={`/couples/${link.id}/disputes`}
            className="inline-flex items-center gap-1 font-medium text-violet-700 hover:underline dark:text-violet-300"
          >
            ⚖ Disputes
          </Link>
          <Link
            href={`/couples/${link.id}/health`}
            className="inline-flex items-center gap-1 font-medium text-emerald-700 hover:underline dark:text-emerald-300"
          >
            📊 Health check-in
          </Link>
          <Link
            href={`/couples/${link.id}/reports`}
            className="inline-flex items-center gap-1 font-medium text-blue-700 hover:underline dark:text-blue-300"
          >
            📰 Weekly reports
          </Link>
          <Link
            href={`/couples/${link.id}/issues`}
            className="inline-flex items-center gap-1 font-medium text-amber-700 hover:underline dark:text-amber-300"
          >
            🔁 Open issues
          </Link>
          <Link
            href={`/couples/${link.id}/preps`}
            className="inline-flex items-center gap-1 font-medium text-fuchsia-700 hover:underline dark:text-fuchsia-300"
          >
            🔒 Prep (private)
          </Link>
        </div>
        <CrossFactConsent
          linkId={link.id}
          yourConsent={yourConsent}
          partnerConsent={partnerConsent}
          partnerName={partnerName}
        />
        <CouplesChat
          conversationId={conversationId}
          currentUserId={user.id}
          partners={partners}
          initialMessages={initialMessages}
          initialTitle="Couples chat"
        />
      </div>
    );
  }

  // Non-active states render the existing detail shell.
  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <Link href="/couples" className="text-sm text-muted-foreground hover:underline">
        ← Couples
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        Invite to {partnerName}
      </h1>
      <p className="mt-1 text-xs text-muted-foreground">
        Created {new Date(link.created_at).toLocaleString()}.
      </p>

      {link.status === "pending" && (
        <section className="mt-6 rounded-md border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
          {youAreCreator
            ? "Waiting for your partner to accept. The invite link expires after 7 days."
            : "You're seeing this because the invite is still pending — refresh after accepting."}
        </section>
      )}

      {(link.status === "revoked" || link.status === "expired") && (
        <section className="mt-6 rounded-md border border-input bg-muted/30 p-4 text-sm">
          {link.status === "revoked"
            ? `Ended ${link.revoked_at ? new Date(link.revoked_at).toLocaleDateString() : ""}.`
            : "This invite expired before it was accepted."}
        </section>
      )}

      {link.status === "pending" && (
        <form action={revokeLink} className="mt-6">
          <input type="hidden" name="id" value={link.id} />
          <button
            type="submit"
            className="rounded-md border border-input bg-background px-3 py-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Cancel invite
          </button>
        </form>
      )}
    </main>
  );
}
