import { redirect } from "next/navigation";
import { TIER_LIMITS, type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { checkInStreak, deleteStreak } from "./actions";
import { CreateStreakForm } from "./CreateStreakForm";

// /tools/drill-sergeant (§9.5.4). Habits + daily check-in + escalation
// preview. The actual cron-driven roasts arrive in the user's "Drill
// Sergeant" conversation (Phase G step 41 service); this page is the
// management surface.

type StreakRow = {
  id: number;
  habit: string;
  current_streak: number;
  longest_streak: number;
  last_checkin_at: string | null;
  created_at: string;
};

export default async function DrillSergeantPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const cap = TIER_LIMITS[tier].drill_sergeant_scheduled; // null = unlimited

  const { data: streaksData } = await supabase
    .from("streaks")
    .select("id, habit, current_streak, longest_streak, last_checkin_at, created_at")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(50);
  const streaks = (streaksData ?? []) as StreakRow[];

  const today = new Date().toISOString().slice(0, 10);

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Drill Sergeant</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Pick a habit. Miss it and the AI escalates — gentle nudge day 1,
          pointed day 3, brutal day 7, eulogy day 14.
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Tier: {tier} ·{" "}
          {cap === null
            ? "unlimited habits"
            : `${streaks.length}/${cap} scheduled habits`}
        </p>
      </header>

      {(cap === null || streaks.length < cap) && (
        <section className="mt-6">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Add a habit
          </h2>
          <div className="mt-3">
            <CreateStreakForm />
          </div>
        </section>
      )}

      <section className="mt-8">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Your habits
        </h2>
        {streaks.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">
            None yet. Pick one above to get the daily push.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-3">
            {streaks.map((s) => (
              <StreakCard
                key={s.id}
                streak={s}
                today={today}
              />
            ))}
          </ul>
        )}
      </section>

      <section className="mt-10 rounded-md border border-input bg-muted/30 p-4 text-xs leading-relaxed text-muted-foreground">
        <p className="font-medium text-foreground">Escalation tiers</p>
        <ul className="mt-2 flex flex-col gap-1">
          <li>· Day 1 miss — gentle nudge</li>
          <li>· Day 3 miss — pointed</li>
          <li>· Day 7 miss — brutal</li>
          <li>· Day 14 miss — eulogy for the goal</li>
        </ul>
        <p className="mt-3">
          Roasts land in your <span className="font-mono">/chat</span> under
          a conversation called <span className="font-mono">Drill Sergeant</span>.
        </p>
      </section>
    </main>
  );
}

function StreakCard({ streak, today }: { streak: StreakRow; today: string }) {
  const last = streak.last_checkin_at;
  const checkedInToday = last === today;
  const daysSince = last
    ? Math.floor(
        (new Date(today).getTime() - new Date(last).getTime()) / 86_400_000,
      )
    : null;

  let status: string;
  let tone: string;
  if (last === null) {
    status = "Not started";
    tone = "border-input bg-muted/30 text-muted-foreground";
  } else if (checkedInToday) {
    status = `Checked in today · streak ${streak.current_streak}`;
    tone = "border-emerald-500/30 bg-emerald-500/5 text-emerald-700";
  } else if (daysSince === 1) {
    status = "Missed yesterday — gentle nudge soon";
    tone = "border-amber-500/30 bg-amber-500/5 text-amber-700";
  } else if (daysSince !== null && daysSince >= 14) {
    status = `Missed ${daysSince} days — eulogy tier`;
    tone = "border-red-500/40 bg-red-500/10 text-red-700";
  } else if (daysSince !== null && daysSince >= 7) {
    status = `Missed ${daysSince} days — brutal tier`;
    tone = "border-red-500/30 bg-red-500/5 text-red-700";
  } else if (daysSince !== null && daysSince >= 3) {
    status = `Missed ${daysSince} days — pointed tier`;
    tone = "border-amber-500/40 bg-amber-500/10 text-amber-700";
  } else {
    status = `Missed ${daysSince} day${daysSince === 1 ? "" : "s"}`;
    tone = "border-input bg-background";
  }

  return (
    <li className={`rounded-md border p-4 shadow-sm ${tone.includes("bg-") ? tone : `${tone}`}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col">
          <span className="text-sm font-medium text-foreground">{streak.habit}</span>
          <span className="mt-1 text-xs text-muted-foreground">
            Current {streak.current_streak} · Longest {streak.longest_streak}
            {last && ` · Last ${last}`}
          </span>
          <span className="mt-1 text-xs">{status}</span>
        </div>
        <div className="flex shrink-0 flex-col gap-1">
          <form action={checkInStreak}>
            <input type="hidden" name="id" value={streak.id} />
            <button
              type="submit"
              disabled={checkedInToday}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {checkedInToday ? "Done" : "Check in"}
            </button>
          </form>
          <form action={deleteStreak}>
            <input type="hidden" name="id" value={streak.id} />
            <button
              type="submit"
              className="rounded-md border border-input bg-background px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              Delete
            </button>
          </form>
        </div>
      </div>
    </li>
  );
}
