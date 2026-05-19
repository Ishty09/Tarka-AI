import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { fetchIncidents } from "@/lib/admin";
import { IncidentRow } from "./IncidentRow";

interface PageProps {
  searchParams?: Promise<{ category?: string; show?: string }>;
}

const CATEGORIES = [
  "crisis",
  "abuse",
  "minor_self_sexualization",
  "jailbreak",
  "spam",
  "harassment",
] as const;

export default async function IncidentsPage({ searchParams }: PageProps) {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const params = (await searchParams) ?? {};
  const category = params.category && CATEGORIES.includes(params.category as (typeof CATEGORIES)[number])
    ? params.category
    : undefined;
  const unreviewedOnly = params.show !== "all";

  const res = await fetchIncidents(user.id, { category, unreviewedOnly });

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h2 className="text-lg font-semibold tracking-tight">Incidents</h2>
        <p className="text-xs text-muted-foreground">
          Safety classifier verdicts surface here. Reviewing closes the loop
          and timestamps your username on the row.
        </p>
      </header>

      <form className="flex flex-wrap items-center gap-2" method="GET">
        <select
          name="category"
          defaultValue={category ?? ""}
          className="rounded-md border border-input bg-background px-2 py-1 text-xs"
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          name="show"
          defaultValue={unreviewedOnly ? "unreviewed" : "all"}
          className="rounded-md border border-input bg-background px-2 py-1 text-xs"
        >
          <option value="unreviewed">Unreviewed only</option>
          <option value="all">All</option>
        </select>
        <button
          type="submit"
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          Filter
        </button>
      </form>

      {!res.ok && (
        <p className="text-xs text-destructive">
          Couldn&apos;t load: {res.status} {res.error}
        </p>
      )}
      {res.ok && res.data.incidents.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No matching incidents. Quiet day.
        </p>
      )}
      {res.ok && (
        <div className="flex flex-col gap-3">
          {res.data.incidents.map((i) => (
            <IncidentRow key={i.id} incident={i} />
          ))}
        </div>
      )}
    </div>
  );
}
