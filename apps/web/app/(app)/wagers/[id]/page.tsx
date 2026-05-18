import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { formatCents, wagerDurationDays } from "@/lib/wagers";
import { cancelPendingWager } from "../actions";
import { CheckinPanel } from "./CheckinPanel";

// Wager detail (§9.5.5). Renders the goal, dates, stake, anti-charity,
// status, and (in step 39) the daily check-in. Step 38 ships the read-
// only surface + a "cancel" button for pending wagers.

interface PageProps {
  params: Promise<{ id: string }>;
}

type WagerRow = {
  id: string;
  goal: string;
  stake_cents: number;
  currency: string;
  status: string;
  start_at: string;
  end_at: string;
  anti_charity_slug: string;
  polar_payment_id: string | null;
  polar_charge_id: string | null;
  evaluation_notes: string | null;
  evaluated_at: string | null;
  created_at: string;
  anti_charity: { name: string; description: string; url: string; ideological_tag: string } | { name: string; description: string; url: string; ideological_tag: string }[] | null;
  referee: { username: string | null; display_name: string | null } | { username: string | null; display_name: string | null }[] | null;
};

function unwrap<T>(v: T | T[] | null): T | null {
  if (!v) return null;
  return Array.isArray(v) ? v[0] ?? null : v;
}

export default async function WagerDetailPage({ params }: PageProps) {
  const { id } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: rowData } = await supabase
    .from("wagers")
    .select(
      "id, goal, stake_cents, currency, status, start_at, end_at, anti_charity_slug, "
      + "polar_payment_id, polar_charge_id, evaluation_notes, evaluated_at, created_at, "
      + "anti_charity:anti_charities!anti_charity_slug(name, description, url, ideological_tag), "
      + "referee:profiles!referee_id(username, display_name)",
    )
    .eq("id", id)
    .eq("user_id", user.id)
    .maybeSingle();
  const wager = rowData as WagerRow | null;
  if (!wager) notFound();

  const charity = unwrap(wager.anti_charity);
  const referee = unwrap(wager.referee);
  const refereeName = referee?.display_name ?? referee?.username ?? null;
  const duration = wagerDurationDays(wager.start_at, wager.end_at);
  const today = new Date();
  const end = new Date(wager.end_at);
  const daysLeft = Math.ceil((end.getTime() - today.getTime()) / 86_400_000);

  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <Link href="/wagers" className="text-sm text-muted-foreground hover:underline">
        ← Wagers
      </Link>

      <header className="mt-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{wager.goal}</h1>
          <p className="mt-2 text-xs text-muted-foreground">
            {formatCents(wager.stake_cents, wager.currency.toUpperCase())} on the line · {duration} day{duration === 1 ? "" : "s"}
            {wager.status === "active" && daysLeft >= 0 && ` · ${daysLeft} day${daysLeft === 1 ? "" : "s"} left`}
          </p>
        </div>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${
            wager.status === "succeeded"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
              : wager.status === "failed"
              ? "border-red-500/40 bg-red-500/10 text-red-700"
              : wager.status === "active"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
              : "border-amber-500/40 bg-amber-500/10 text-amber-700"
          }`}
        >
          {wager.status}
        </span>
      </header>

      <section className="mt-6 grid gap-4 sm:grid-cols-2">
        <Card label="Start">{new Date(wager.start_at).toLocaleDateString()}</Card>
        <Card label="End">{new Date(wager.end_at).toLocaleDateString()}</Card>
        <Card label="Anti-charity">
          <div className="flex flex-col gap-1 text-sm">
            <span className="font-medium">{charity?.name ?? wager.anti_charity_slug}</span>
            {charity?.description && (
              <span className="text-[11px] text-muted-foreground">{charity.description}</span>
            )}
            {charity?.url && (
              <a
                href={charity.url}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] underline"
              >
                {charity.url.replace(/^https?:\/\//, "")}
              </a>
            )}
          </div>
        </Card>
        <Card label="Referee">
          {refereeName ?? (
            <span className="text-xs text-muted-foreground">
              AI evaluation — based on your check-ins
            </span>
          )}
        </Card>
      </section>

      {wager.evaluated_at && wager.evaluation_notes && (
        <section className="mt-6 rounded-md border border-input bg-muted/30 p-4 text-sm">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Evaluator notes
          </h2>
          <p className="mt-2 leading-relaxed">{wager.evaluation_notes}</p>
          <p className="mt-2 text-[10px] text-muted-foreground">
            Evaluated {new Date(wager.evaluated_at).toLocaleString()}
          </p>
        </section>
      )}

      {wager.status === "pending" && (
        <form action={cancelPendingWager} className="mt-6">
          <input type="hidden" name="id" value={wager.id} />
          <button
            type="submit"
            className="rounded-md border border-input bg-background px-3 py-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Cancel before authorisation
          </button>
        </form>
      )}

      {wager.status === "active" && (
        <ActiveCheckins wagerId={wager.id} startAt={wager.start_at} endAt={wager.end_at} />
      )}
    </main>
  );
}

async function ActiveCheckins({
  wagerId,
  startAt,
  endAt,
}: {
  wagerId: string;
  startAt: string;
  endAt: string;
}) {
  const supabase = await createServerSupabase();
  const { data: checkinsData } = await supabase
    .from("wager_checkins")
    .select("checkin_date, status, notes, proof_url")
    .eq("wager_id", wagerId)
    .order("checkin_date", { ascending: true })
    .limit(400);
  const checkins = (checkinsData ?? []) as Array<{
    checkin_date: string;
    status: "completed" | "missed" | "skipped";
    notes: string | null;
    proof_url: string | null;
  }>;
  const todayIso = new Date().toISOString().slice(0, 10);
  return (
    <CheckinPanel
      wagerId={wagerId}
      startAt={startAt}
      endAt={endAt}
      todayIso={todayIso}
      checkins={checkins}
    />
  );
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-input bg-background p-3 shadow-sm">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}
