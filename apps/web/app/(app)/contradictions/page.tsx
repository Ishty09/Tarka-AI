import { redirect } from "next/navigation";
import { TIER_LIMITS, type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { dismissContradiction, acknowledgeContradiction } from "./actions";

// Contradiction Wall (§9.4.1). Server-rendered list joined with the two
// implicated user_facts via embedded foreign-key selects. Sorted by severity
// desc; dismissed rows hidden by default; tier-based depth filter caps how
// far back we look.
//
// Severity bar is plain HTML — Tremor (§3) would be the §9.4.1 timeline
// chart but it's overkill for the MVP rendering. Bars convey rank well
// enough until the volume justifies it.

interface PageProps {
  searchParams: Promise<{ show?: string }>;
}

type EmbeddedFact = { id: number; fact: string; category: string | null; created_at: string };
type Row = {
  id: number;
  severity: number;
  summary: string;
  surfaced_at: string | null;
  acknowledged_at: string | null;
  dismissed_at: string | null;
  created_at: string;
  fact_a: EmbeddedFact | EmbeddedFact[] | null;
  fact_b: EmbeddedFact | EmbeddedFact[] | null;
};

function asFact(value: EmbeddedFact | EmbeddedFact[] | null): EmbeddedFact | null {
  if (!value) return null;
  return Array.isArray(value) ? (value[0] ?? null) : value;
}

export default async function ContradictionsPage({ searchParams }: PageProps) {
  const { show } = await searchParams;
  const showDismissed = show === "dismissed";

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const depthDays = TIER_LIMITS[tier].contradiction_wall_depth_days;

  let query = supabase
    .from("contradictions")
    .select(
      "id, severity, summary, surfaced_at, acknowledged_at, dismissed_at, created_at, fact_a:fact_a_id (id, fact, category, created_at), fact_b:fact_b_id (id, fact, category, created_at)",
    )
    .eq("user_id", user.id)
    .order("severity", { ascending: false })
    .limit(100);

  if (depthDays !== null) {
    const cutoff = new Date(Date.now() - depthDays * 86_400_000).toISOString();
    query = query.gte("created_at", cutoff);
  }

  if (showDismissed) {
    query = query.not("dismissed_at", "is", null);
  } else {
    query = query.is("dismissed_at", null);
  }

  const { data: rowsData } = await query;
  const rows = (rowsData ?? []) as unknown as Row[];

  return (
    <main className="mx-auto w-full max-w-4xl p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Contradiction Wall</h1>
        <div className="flex items-center gap-2">
          <a
            href={showDismissed ? "/contradictions" : "/contradictions?show=dismissed"}
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-2 text-sm font-medium shadow-sm hover:bg-accent"
          >
            {showDismissed ? "Active" : "Dismissed"}
          </a>
        </div>
      </div>

      <p className="mt-1 text-xs text-muted-foreground">
        {depthDays === null
          ? "Showing everything we have."
          : `Showing the last ${depthDays} days. ${tier === "free" ? "Upgrade for deeper history." : ""}`}
      </p>

      {rows.length === 0 ? (
        <p className="mt-10 text-sm text-muted-foreground">
          {showDismissed
            ? "Nothing dismissed yet."
            : "No contradictions surfaced yet. Talk more — patterns take a few turns."}
        </p>
      ) : (
        <ul className="mt-6 flex flex-col gap-3">
          {rows.map((row) => {
            const factA = asFact(row.fact_a);
            const factB = asFact(row.fact_b);
            return (
              <li
                key={row.id}
                className={`rounded-md border border-input bg-background p-4 shadow-sm ${
                  row.dismissed_at ? "opacity-60" : ""
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-3">
                    <SeverityBar severity={row.severity} />
                    <p className="text-sm font-medium">{row.summary}</p>
                    <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                      <FactBox label="Earlier" fact={factA && factB && factA.created_at <= factB.created_at ? factA : factB} />
                      <FactBox label="Later" fact={factA && factB && factA.created_at > factB.created_at ? factA : factB} />
                    </div>
                  </div>
                  {!row.dismissed_at && (
                    <div className="flex shrink-0 flex-col gap-2">
                      {!row.acknowledged_at && (
                        <form action={acknowledgeContradiction}>
                          <input type="hidden" name="id" value={row.id} />
                          <button
                            type="submit"
                            className="rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent"
                          >
                            Acknowledge
                          </button>
                        </form>
                      )}
                      <form action={dismissContradiction}>
                        <input type="hidden" name="id" value={row.id} />
                        <button
                          type="submit"
                          className="rounded-md border border-input bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                        >
                          Dismiss
                        </button>
                      </form>
                    </div>
                  )}
                </div>
                {row.acknowledged_at && !row.dismissed_at && (
                  <p className="mt-3 text-xs text-muted-foreground">
                    Acknowledged {new Date(row.acknowledged_at).toLocaleDateString()}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

function SeverityBar({ severity }: { severity: number }) {
  // Clamp + scale to a 0-100% width. Colour banding ties to the §9.4.1
  // severity scale: low (grey), mid (amber), high (red).
  const pct = Math.min(100, Math.max(0, severity * 10));
  const tone = severity >= 7 ? "bg-red-500" : severity >= 4 ? "bg-amber-500" : "bg-muted-foreground";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
        <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-muted-foreground">{severity}/10</span>
    </div>
  );
}

function FactBox({ label, fact }: { label: string; fact: EmbeddedFact | null }) {
  if (!fact) return null;
  return (
    <div className="rounded-md border border-input bg-muted/30 p-2">
      <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wide">
        <span>{label}</span>
        <time>{new Date(fact.created_at).toLocaleDateString()}</time>
      </div>
      <p className="text-xs text-foreground">{fact.fact}</p>
      {fact.category && (
        <p className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
          {fact.category}
        </p>
      )}
    </div>
  );
}
