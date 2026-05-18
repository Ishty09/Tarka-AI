import Link from "next/link";
import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { maxSeatsForTier } from "@/lib/groups";

// Groups list (§9.3.4). Two states:
//   - paid tier with rooms → render list
//   - free tier or empty → upsell / empty copy

type GroupRow = {
  id: string;
  name: string;
  archived: boolean;
  owner_id: string;
  max_members: number;
  created_at: string;
  members: { user_id: string }[];
};

export default async function GroupsPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const seatCap = maxSeatsForTier(tier);

  // Membership rows tell us which groups the user is in. RLS doesn't
  // let us read group_rooms across users we don't share a room with, so
  // we resolve membership first then fetch the rooms.
  const { data: memberships } = await supabase
    .from("group_members")
    .select("group_id, role, group:group_rooms(id, name, archived, owner_id, max_members, created_at)")
    .eq("user_id", user.id);

  const rooms = (memberships ?? [])
    .map((m) => {
      const room = Array.isArray(m.group) ? m.group[0] : m.group;
      return room
        ? ({ ...room, members: [] } as GroupRow)
        : null;
    })
    .filter((r): r is GroupRow => r !== null);

  const active = rooms.filter((r) => !r.archived);
  const archived = rooms.filter((r) => r.archived);

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Groups</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Slack-style chats with up to {seatCap} people, mediated by an AI.
            Useful for housemate disputes, founder splits, family decisions.
          </p>
        </div>
        {seatCap > 0 ? (
          <Link
            href="/groups/create"
            className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            Create room
          </Link>
        ) : (
          <Link
            href="/pricing"
            className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            Upgrade to create
          </Link>
        )}
      </div>

      <p className="mt-2 text-xs text-muted-foreground">
        Tier: {tier} · {seatCap === 0 ? "no group rooms" : `${seatCap} seats per room`}
      </p>

      {active.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Active rooms
          </h2>
          <ul className="mt-3 flex flex-col gap-2">
            {active.map((g) => (
              <li key={g.id}>
                <Link
                  href={`/groups/${g.id}`}
                  className="flex items-center justify-between rounded-md border border-input bg-background px-4 py-3 text-sm shadow-sm hover:bg-accent"
                >
                  <div className="flex flex-col">
                    <span className="font-medium">{g.name}</span>
                    <span className="text-xs text-muted-foreground">
                      Max {g.max_members} seats · created {new Date(g.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {g.owner_id === user.id ? "Owner" : "Member"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {archived.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Archived
          </h2>
          <ul className="mt-3 flex flex-col gap-2">
            {archived.map((g) => (
              <li
                key={g.id}
                className="flex items-center justify-between rounded-md border border-input bg-muted/30 px-4 py-3 text-sm opacity-70"
              >
                <span>{g.name}</span>
                <span className="text-xs text-muted-foreground">Archived</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {rooms.length === 0 && (
        <p className="mt-10 text-sm text-muted-foreground">
          {seatCap === 0
            ? "Upgrade to start a group room."
            : "No rooms yet. Create one to get started."}
        </p>
      )}
    </main>
  );
}
