import { redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { SettingsSection } from "../_components/SettingsSection";
import { CrossFactToggle } from "./CrossFactToggle";

// §12.3 — Privacy. Lists every active couple link with its cross-fact toggle
// per-side, plus a brief Roast Feed visibility note. The audit_log table is
// admin-only (§6.7 audit_log_admin); we surface the user-readable equivalent
// instead — couple_link history with timestamps.

type CoupleLinkRow = {
  id: string;
  user_a: string;
  user_b: string | null;
  status: string;
  cross_fact_consent_a: boolean;
  cross_fact_consent_b: boolean;
  created_at: string;
  revoked_at: string | null;
};

export default async function PrivacyPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: linksRaw } = await supabase
    .from("couple_links")
    .select(
      "id, user_a, user_b, status, cross_fact_consent_a, cross_fact_consent_b, created_at, revoked_at",
    )
    .or(`user_a.eq.${user.id},user_b.eq.${user.id}`)
    .order("created_at", { ascending: false })
    .limit(50);
  const links = (linksRaw ?? []) as CoupleLinkRow[];
  const active = links.filter((l) => l.status === "active");

  // Fetch partner usernames in one batch for active links.
  const partnerIds = active
    .map((l) => (l.user_a === user.id ? l.user_b : l.user_a))
    .filter((id): id is string => Boolean(id));
  const partnersById = new Map<string, string>();
  if (partnerIds.length > 0) {
    const { data: partnerRows } = await supabase
      .from("profiles")
      .select("id, username, display_name")
      .in("id", partnerIds);
    for (const p of (partnerRows ?? []) as { id: string; username: string; display_name: string | null }[]) {
      partnersById.set(p.id, p.display_name ?? `@${p.username}`);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <SettingsSection
        title="Couples cross-fact retrieval"
        description="When you and your partner both consent, mediation can reference each of your tracked facts. Either of you can revoke at any time."
      >
        {active.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            You don&apos;t have any active couple links.{" "}
            <Link href="/couples" className="underline">
              Invite a partner →
            </Link>
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {active.map((link) => {
              const iAmA = link.user_a === user.id;
              const partnerId = iAmA ? link.user_b : link.user_a;
              const partnerName = partnerId
                ? partnersById.get(partnerId) ?? "partner"
                : "partner";
              const myConsent = iAmA
                ? link.cross_fact_consent_a
                : link.cross_fact_consent_b;
              const partnerConsent = iAmA
                ? link.cross_fact_consent_b
                : link.cross_fact_consent_a;
              return (
                <CrossFactToggle
                  key={link.id}
                  coupleLinkId={link.id}
                  partnerName={partnerName}
                  enabled={myConsent}
                  partnerConsent={partnerConsent}
                />
              );
            })}
          </div>
        )}
      </SettingsSection>

      <SettingsSection
        title="Roast Feed visibility"
        description="Each post you share to the public feed is checked again at submission time. You stay anonymous by default; the share dialog lets you opt into a username byline per post."
      >
        <Link href="/feed" className="text-sm underline">
          Open the feed →
        </Link>
      </SettingsSection>

      <SettingsSection
        title="Couple link history"
        description="Recent invites, accepts, and revokes."
      >
        {links.length === 0 ? (
          <p className="text-sm text-muted-foreground">No history yet.</p>
        ) : (
          <ul className="flex flex-col gap-2 text-xs">
            {links.map((link) => (
              <li
                key={link.id}
                className="flex items-center justify-between rounded-md border border-input px-3 py-2"
              >
                <span>
                  <span className="font-medium uppercase tracking-wide">
                    {link.status}
                  </span>{" "}
                  <span className="text-muted-foreground">
                    {new Date(link.created_at).toLocaleDateString()}
                    {link.revoked_at &&
                      ` → revoked ${new Date(link.revoked_at).toLocaleDateString()}`}
                  </span>
                </span>
                <Link
                  href={`/couples/${link.id}`}
                  className="text-muted-foreground hover:text-foreground"
                >
                  Open →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </SettingsSection>
    </div>
  );
}
