import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { DiagnosticsView } from "./DiagnosticsView";

// /diagnostics — single-page system health snapshot. Visible to any
// signed-in user (no admin gate) because the data is scoped to their
// own account + system-level health that doesn't expose secrets.
// Use this when "X is broken" reports come in to figure out which
// surface (web / workers / DB / data) is actually the problem.

export default async function DiagnosticsPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Diagnostics</h1>
        <p className="text-sm text-muted-foreground">
          Live status of every surface the app talks to. Refresh this
          page to re-run all probes.
        </p>
      </header>
      <DiagnosticsView />
    </main>
  );
}
