import { TIER_LIMITS, type Tier } from "@quarrel/shared/constants";

// Full feature comparison from §8.1. Driven straight off TIER_LIMITS so
// the matrix can't drift from the values quotas.py enforces.

type Cell = string;

interface Row {
  feature: string;
  values: Record<Tier, Cell>;
}

function fmt(n: number | null, suffix: string = "", unlimited = "Unlimited"): Cell {
  if (n === null) return unlimited;
  return `${n.toLocaleString("en-US")}${suffix}`;
}

const ROWS: Row[] = (() => {
  const f = TIER_LIMITS.free;
  const p = TIER_LIMITS.pro;
  const m = TIER_LIMITS.max;

  const councilCell = (t: typeof f): Cell =>
    `${t.council_runs.limit} / ${t.council_runs.period}`;

  type TypedMirror = "read_past_only" | "weekly" | "weekly_and_on_demand";
  const mirrorLabel: Record<TypedMirror, Cell> = {
    read_past_only: "Read past reports",
    weekly: "Weekly",
    weekly_and_on_demand: "Weekly + on-demand",
  };

  const eulogyLabel = (
    v: "quarterly" | "quarterly_and_on_demand" | null,
  ): Cell => {
    if (v === null) return "—";
    if (v === "quarterly") return "Quarterly";
    return "Quarterly + on-demand";
  };

  const ctxLabel = (n: number): Cell =>
    n >= 1_000_000
      ? `${(n / 1_000_000).toFixed(0)}M tokens`
      : n >= 1_000
      ? `${(n / 1_000).toFixed(0)}K tokens`
      : `${n} tokens`;

  return [
    {
      feature: "Messages / day",
      values: {
        free: fmt(f.messages_per_day),
        pro: fmt(p.messages_per_day),
        max: fmt(m.messages_per_day),
      },
    },
    {
      feature: "Council runs",
      values: {
        free: councilCell(f),
        pro: councilCell(p),
        max: councilCell(m),
      },
    },
    {
      feature: "Active personas",
      values: {
        free: fmt(f.active_personas),
        pro: fmt(p.active_personas),
        max: fmt(m.active_personas),
      },
    },
    {
      feature: "Couple links",
      values: {
        free: f.couple_links_active === 0 ? "—" : fmt(f.couple_links_active),
        pro: fmt(p.couple_links_active),
        max: fmt(m.couple_links_active),
      },
    },
    {
      feature: "Group room seats",
      values: {
        free: f.group_seats_per_room === 0 ? "—" : fmt(f.group_seats_per_room),
        pro: fmt(p.group_seats_per_room),
        max: fmt(m.group_seats_per_room),
      },
    },
    {
      feature: "Active wagers",
      values: {
        free: f.wager_active_stakes === 0 ? "—" : fmt(f.wager_active_stakes),
        pro: `${p.wager_active_stakes}, max $${p.wager_max_stake_cents / 100}`,
        max: `${m.wager_active_stakes}, max $${m.wager_max_stake_cents / 100}`,
      },
    },
    {
      feature: "Roast Feed posts / week",
      values: {
        free: f.roast_feed_posts_per_week === 0 ? "Read-only" : fmt(f.roast_feed_posts_per_week),
        pro: fmt(p.roast_feed_posts_per_week),
        max: fmt(m.roast_feed_posts_per_week),
      },
    },
    {
      feature: "Persona marketplace earnings",
      values: {
        free: f.persona_earnings_cap_cents_per_month === 0 ? "—" : `$${f.persona_earnings_cap_cents_per_month / 100} / mo`,
        pro: `$${p.persona_earnings_cap_cents_per_month / 100} / mo`,
        max: `$${m.persona_earnings_cap_cents_per_month / 100} / mo`,
      },
    },
    {
      feature: "Contradiction memory depth",
      values: {
        free: fmt(f.contradiction_wall_depth_days, " days", "Forever"),
        pro: fmt(p.contradiction_wall_depth_days, " days", "Forever"),
        max: fmt(m.contradiction_wall_depth_days, " days", "Forever"),
      },
    },
    {
      feature: "Context window",
      values: {
        free: ctxLabel(f.context_window_tokens),
        pro: ctxLabel(p.context_window_tokens),
        max: ctxLabel(m.context_window_tokens),
      },
    },
    {
      feature: "Mirror Mode",
      values: {
        free: mirrorLabel[f.mirror_mode as TypedMirror],
        pro: mirrorLabel[p.mirror_mode as TypedMirror],
        max: mirrorLabel[m.mirror_mode as TypedMirror],
      },
    },
    {
      feature: "Eulogy Test",
      values: {
        free: eulogyLabel(f.eulogy_cadence),
        pro: eulogyLabel(p.eulogy_cadence),
        max: eulogyLabel(m.eulogy_cadence),
      },
    },
    {
      feature: "Voice / month (later)",
      values: {
        free: `${f.voice_minutes_per_month} min`,
        pro: `${p.voice_minutes_per_month} min`,
        max: `${m.voice_minutes_per_month} min`,
      },
    },
    {
      feature: "Drill Sergeant streaks",
      values: {
        free: fmt(f.drill_sergeant_scheduled),
        pro: fmt(p.drill_sergeant_scheduled),
        max: fmt(m.drill_sergeant_scheduled),
      },
    },
  ];
})();

export function ComparisonTable() {
  return (
    <section className="overflow-x-auto rounded-xl border bg-card">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b text-left">
            <th scope="col" className="w-1/3 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Feature
            </th>
            <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Free
            </th>
            <th scope="col" className="bg-foreground/[0.03] px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Pro
            </th>
            <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Max
            </th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.feature} className="border-b last:border-b-0">
              <th
                scope="row"
                className="px-4 py-3 text-left font-medium text-foreground"
              >
                {row.feature}
              </th>
              <td className="px-4 py-3 text-muted-foreground">{row.values.free}</td>
              <td className="bg-foreground/[0.03] px-4 py-3 text-muted-foreground">
                {row.values.pro}
              </td>
              <td className="px-4 py-3 text-muted-foreground">{row.values.max}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
