import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { fetchUsers } from "@/lib/admin";
import { UserRow } from "./UserRow";

interface PageProps {
  searchParams?: Promise<{ q?: string }>;
}

export default async function UsersPage({ searchParams }: PageProps) {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const params = (await searchParams) ?? {};
  const query = params.q?.trim() || undefined;
  const res = await fetchUsers(user.id, query);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h2 className="text-lg font-semibold tracking-tight">Users</h2>
        <p className="text-xs text-muted-foreground">
          Search by username or display name. Suspending a user blocks chat,
          tools, and Wagers immediately and is logged to audit_log.
        </p>
      </header>

      <form className="flex items-center gap-2" method="GET">
        <input
          type="text"
          name="q"
          defaultValue={query ?? ""}
          placeholder="username or display name"
          maxLength={120}
          className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
        />
        <button
          type="submit"
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          Search
        </button>
      </form>

      {!res.ok && (
        <p className="text-xs text-destructive">
          Couldn&apos;t load: {res.status} {res.error}
        </p>
      )}
      {res.ok && res.data.users.length === 0 && (
        <p className="text-sm text-muted-foreground">No matches.</p>
      )}
      {res.ok && (
        <div className="flex flex-col gap-3">
          {res.data.users.map((u) => (
            <UserRow key={u.id} user={u} />
          ))}
        </div>
      )}
    </div>
  );
}
