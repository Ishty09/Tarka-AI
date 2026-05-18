import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { revokeLink } from "../actions";

// /couples/[linkId] — single-link detail.
// §9.3.1 lists four UI states (pending / awaiting-consent / active /
// revoked); step 33 ships the pending + active shells. Step 34 brings
// in the shared chat; step 35 brings the cross-fact consent toggle.

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

  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <Link href="/couples" className="text-sm text-muted-foreground hover:underline">
        ← Couples
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        {link.status === "active" ? `You + ${partnerName}` : `Invite to ${partnerName}`}
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

      {link.status === "active" && (
        <section className="mt-6 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm">
          <p className="font-medium">Link is active.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Cross-fact consent: you {link.consent_a && link.consent_b
              ? "and your partner"
              : ""}{" "}
            haven&apos;t toggled it on yet. Mediation works without it; turning
            it on lets the AI reference what you&apos;ve each told it
            separately. (Toggle ships next step.)
          </p>
        </section>
      )}

      {(link.status === "revoked" || link.status === "expired") && (
        <section className="mt-6 rounded-md border border-input bg-muted/30 p-4 text-sm">
          {link.status === "revoked"
            ? `Ended ${link.revoked_at ? new Date(link.revoked_at).toLocaleDateString() : ""}.`
            : "This invite expired before it was accepted."}
        </section>
      )}

      {link.status !== "revoked" && link.status !== "expired" && (
        <form action={revokeLink} className="mt-6">
          <input type="hidden" name="id" value={link.id} />
          <button
            type="submit"
            className="rounded-md border border-input bg-background px-3 py-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            End this link
          </button>
        </form>
      )}
    </main>
  );
}
