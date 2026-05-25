import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { DailyLogForm } from "./DailyLogForm";
import { EffortChart } from "./EffortChart";

interface PageProps {
  params: Promise<{ linkId: string }>;
}

interface LogRow {
  id: string;
  user_id: string;
  log_date: string;
  effort_rating: number;
  partner_appreciation: string | null;
  frustration: string | null;
}

export default async function HealthDashboardPage({ params }: PageProps) {
  const { linkId } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: link } = await supabase
    .from("couple_links")
    .select(
      "user_a, user_b, status, partner_a:profiles!user_a(display_name, username), partner_b:profiles!user_b(display_name, username)"
    )
    .eq("id", linkId)
    .maybeSingle();
  if (!link || link.status !== "active") redirect("/couples");
  if (user.id !== link.user_a && user.id !== link.user_b) redirect("/couples");

  const unwrap = <T,>(v: T | T[] | null) =>
    Array.isArray(v) ? v[0] ?? null : v;
  const aProfile = unwrap(link.partner_a as { display_name: string | null; username: string | null } | { display_name: string | null; username: string | null }[] | null);
  const bProfile = unwrap(link.partner_b as { display_name: string | null; username: string | null } | { display_name: string | null; username: string | null }[] | null);
  const aName = aProfile?.display_name ?? aProfile?.username ?? "Partner A";
  const bName = bProfile?.display_name ?? bProfile?.username ?? "Partner B";

  // Last 7 days of logs for both partners.
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 6);
  const fromDate = sevenDaysAgo.toISOString().slice(0, 10);

  const { data: rawLogs } = await supabase
    .from("couple_health_logs")
    .select(
      "id, user_id, log_date, effort_rating, partner_appreciation, frustration"
    )
    .eq("couple_link_id", linkId)
    .gte("log_date", fromDate)
    .order("log_date", { ascending: true });
  const logs: LogRow[] = (rawLogs ?? []) as unknown as LogRow[];

  const isA = user.id === link.user_a;
  const today = new Date().toISOString().slice(0, 10);
  const todayLog = logs.find((l) => l.user_id === user.id && l.log_date === today) ?? null;

  // Build 7-day series for both partners (fill missing days with null).
  const series = buildSeries(logs, link.user_a, link.user_b ?? "");

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <Link
        href={`/couples/${linkId}`}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ← Back to couple
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Health dashboard</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        1 minute per day, both of you. The graph shows the last 7 days of
        effort. The weekly report uses these check-ins to surface patterns.
      </p>

      {/* Today's check-in form */}
      <section className="mt-6 rounded-lg border border-input bg-card p-4">
        <h2 className="text-sm font-semibold">
          {todayLog ? "Today's check-in (saved)" : "Today's check-in"}
        </h2>
        <DailyLogForm
          linkId={linkId}
          initial={todayLog}
        />
      </section>

      {/* 7-day effort graph */}
      <section className="mt-6 rounded-lg border border-input bg-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Effort, last 7 days</h2>
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-emerald-500" />
              {aName}
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-violet-500" />
              {bName}
            </span>
          </div>
        </div>
        <EffortChart series={series} aName={aName} bName={bName} />
      </section>

      {/* Recent appreciations + frustrations from your partner */}
      <section className="mt-6 grid gap-3 md:grid-cols-2">
        <RecentNotesCard
          title={`From ${isA ? bName : aName}: appreciation`}
          tone="emerald"
          items={logs
            .filter((l) => l.user_id !== user.id && l.partner_appreciation)
            .slice(-3)
            .reverse()
            .map((l) => ({ date: l.log_date, text: l.partner_appreciation! }))}
        />
        <RecentNotesCard
          title={`From ${isA ? bName : aName}: frustration`}
          tone="amber"
          items={logs
            .filter((l) => l.user_id !== user.id && l.frustration)
            .slice(-3)
            .reverse()
            .map((l) => ({ date: l.log_date, text: l.frustration! }))}
        />
      </section>
    </main>
  );
}

function buildSeries(logs: LogRow[], userA: string, userB: string) {
  const today = new Date();
  const days: { date: string; a: number | null; b: number | null }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    days.push({ date: d.toISOString().slice(0, 10), a: null, b: null });
  }
  for (const l of logs) {
    const slot = days.find((d) => d.date === l.log_date);
    if (!slot) continue;
    if (l.user_id === userA) slot.a = l.effort_rating;
    if (l.user_id === userB) slot.b = l.effort_rating;
  }
  return days;
}

function RecentNotesCard({
  title,
  tone,
  items,
}: {
  title: string;
  tone: "emerald" | "amber";
  items: { date: string; text: string }[];
}) {
  const cls =
    tone === "emerald"
      ? "border-emerald-500/30 bg-emerald-500/5"
      : "border-amber-500/30 bg-amber-500/5";
  return (
    <div className={`rounded-lg border p-4 ${cls}`}>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {items.length === 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">No notes yet.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {items.map((it) => (
            <li key={it.date} className="text-sm">
              <span className="text-[11px] text-muted-foreground">
                {new Date(it.date).toLocaleDateString()}
              </span>
              <p className="mt-0.5 leading-relaxed">{it.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
