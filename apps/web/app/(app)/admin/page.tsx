import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import {
  fetchIncidents,
  fetchPendingFeedPosts,
  fetchPendingPersonas,
} from "@/lib/admin";

// Dashboard — three small counters and a tile per surface. Reads happen in
// parallel; if the workers admin API is down we still render the page with
// zeros so the admin can at least navigate.

export default async function AdminDashboard() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const [personas, posts, incidents] = await Promise.all([
    fetchPendingPersonas(user.id),
    fetchPendingFeedPosts(user.id),
    fetchIncidents(user.id),
  ]);

  const personaCount = personas.ok ? personas.data.personas.length : 0;
  const postCount = posts.ok ? posts.data.posts.length : 0;
  const incidentCount = incidents.ok ? incidents.data.incidents.length : 0;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Admin dashboard</h2>
        <p className="text-sm text-muted-foreground">
          Counts reflect pending or unreviewed items only.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Tile
          href="/admin/moderation"
          label="Moderation queue"
          count={personaCount + postCount}
          subtext={`${personaCount} personas · ${postCount} feed posts`}
        />
        <Tile href="/admin/users" label="Users" count={null} subtext="Search + suspend" />
        <Tile
          href="/admin/incidents"
          label="Unreviewed incidents"
          count={incidentCount}
          subtext="Crisis · abuse · jailbreak"
        />
      </div>

      {(!personas.ok || !posts.ok || !incidents.ok) && (
        <p className="text-xs text-amber-600">
          One or more admin reads failed.{" "}
          {[personas, posts, incidents]
            .filter((r) => !r.ok)
            .map((r) => (r.ok ? "" : `${r.status} ${r.error}`))
            .join(" / ")}
        </p>
      )}
    </div>
  );
}

function Tile({
  href,
  label,
  count,
  subtext,
}: {
  href: string;
  label: string;
  count: number | null;
  subtext: string;
}) {
  return (
    <Link
      href={href}
      className="flex flex-col gap-1 rounded-lg border border-input bg-card p-4 shadow-sm hover:bg-accent"
    >
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-3xl font-semibold tracking-tight">
        {count === null ? "—" : count}
      </span>
      <span className="text-xs text-muted-foreground">{subtext}</span>
    </Link>
  );
}
