import Link from "next/link";
import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { activeCoupleLimitFor } from "@/lib/couples";
import { revokeLink } from "./actions";

// Couples list (§9.3.1). Shows every couple_link the user participates in,
// grouped by status. Empty state for free tier points at /pricing.

type LinkRow = {
  id: string;
  user_a: string;
  user_b: string | null;
  status: string;
  invite_code: string | null;
  invite_expires_at: string | null;
  created_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
  consent_a: boolean;
  consent_b: boolean;
  partner_a: { username: string | null; display_name: string | null } | { username: string | null; display_name: string | null }[] | null;
  partner_b: { username: string | null; display_name: string | null } | { username: string | null; display_name: string | null }[] | null;
};

function unwrap<T>(v: T | T[] | null): T | null {
  if (!v) return null;
  return Array.isArray(v) ? v[0] ?? null : v;
}

export default async function CouplesPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const limit = activeCoupleLimitFor(tier);

  const { data: linksData } = await supabase
    .from("couple_links")
    .select(
      "id, user_a, user_b, status, invite_code, invite_expires_at, created_at, revoked_at, revoked_by, consent_a, consent_b, "
      + "partner_a:profiles!user_a(username, display_name), "
      + "partner_b:profiles!user_b(username, display_name)"
    )
    .or(`user_a.eq.${user.id},user_b.eq.${user.id}`)
    .order("created_at", { ascending: false })
    .limit(50);
  const links = (linksData ?? []) as unknown as LinkRow[];

  const active = links.filter((l) => l.status === "active");
  const pending = links.filter((l) => l.status === "pending");
  const archived = links.filter((l) => l.status === "revoked" || l.status === "expired");

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Couples</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Shared chats with one other person. The AI mediates honestly — not
            therapy, not validation.
          </p>
        </div>
        {limit > 0 ? (
          <Link
            href="/couples/invite"
            className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            Invite partner
          </Link>
        ) : (
          <Link
            href="/pricing"
            className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            Upgrade to invite
          </Link>
        )}
      </div>

      <p className="mt-2 text-xs text-muted-foreground">
        Tier: {tier} · cap {limit} active link{limit === 1 ? "" : "s"}.
      </p>

      <Section title="Active" links={active} currentUserId={user.id} variant="active" />
      <Section title="Pending invites" links={pending} currentUserId={user.id} variant="pending" />
      <Section title="Archived" links={archived} currentUserId={user.id} variant="archived" />

      {links.length === 0 && (
        <p className="mt-10 text-sm text-muted-foreground">
          No couple links yet. {limit > 0 ? "Invite your partner to start one." : "Upgrade to start one."}
        </p>
      )}
    </main>
  );
}

function Section({
  title,
  links,
  currentUserId,
  variant,
}: {
  title: string;
  links: LinkRow[];
  currentUserId: string;
  variant: "active" | "pending" | "archived";
}) {
  if (links.length === 0) return null;
  return (
    <section className="mt-8">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      <ul className="mt-3 flex flex-col gap-3">
        {links.map((link) => {
          const youAreCreator = link.user_a === currentUserId;
          const otherProfile = unwrap(youAreCreator ? link.partner_b : link.partner_a);
          return (
            <li
              key={link.id}
              className="flex flex-col gap-2 rounded-md border border-input bg-background px-4 py-3 shadow-sm sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex flex-col text-sm">
                <span className="font-medium">
                  {variant === "pending"
                    ? youAreCreator
                      ? "Waiting for your partner to accept"
                      : "Pending"
                    : `You · ${otherProfile?.display_name ?? otherProfile?.username ?? "Partner"}`}
                </span>
                <span className="text-xs text-muted-foreground">
                  {variant === "pending" && youAreCreator && link.invite_code && (
                    <>
                      Share link · expires{" "}
                      {link.invite_expires_at
                        ? new Date(link.invite_expires_at).toLocaleDateString()
                        : "—"}
                    </>
                  )}
                  {variant === "active" && `Created ${new Date(link.created_at).toLocaleDateString()}`}
                  {variant === "archived"
                    && (link.status === "revoked"
                      ? `Ended ${link.revoked_at ? new Date(link.revoked_at).toLocaleDateString() : ""}`
                      : "Invite expired")}
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {variant === "pending" && youAreCreator && link.invite_code && (
                  <>
                    <code className="rounded-md border border-input bg-muted/30 px-2 py-1 text-xs">
                      {link.invite_code}
                    </code>
                    <CopyLinkButton code={link.invite_code} />
                  </>
                )}
                {variant === "active" && (
                  <Link
                    href={`/couples/${link.id}`}
                    className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
                  >
                    Open
                  </Link>
                )}
                {(variant === "active" || variant === "pending") && (
                  <form action={revokeLink}>
                    <input type="hidden" name="id" value={link.id} />
                    <button
                      type="submit"
                      className="rounded-md border border-input bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                    >
                      {variant === "pending" ? "Cancel" : "End link"}
                    </button>
                  </form>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function CopyLinkButton({ code }: { code: string }) {
  return (
    <a
      href={`/couples/join/${code}`}
      className="rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent"
      target="_blank"
      rel="noreferrer"
    >
      Open invite
    </a>
  );
}
