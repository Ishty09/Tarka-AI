import { redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";

// Admin auth gate — refuses any non-admin profile. Defense in depth: the
// workers admin routes re-check is_admin on every call (see services/admin.py
// require_admin), so a stale RSC render or a manually-poked URL can't bypass
// the actual mutation surface.

const SECTIONS = [
  { href: "/admin", label: "Dashboard" },
  { href: "/admin/moderation", label: "Moderation" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/incidents", label: "Incidents" },
] as const;

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("is_admin")
    .eq("id", user.id)
    .maybeSingle();
  if (!profile?.is_admin) redirect("/chat");

  return (
    <div className="mx-auto flex w-full max-w-6xl gap-8 p-6">
      <aside className="w-48 shrink-0">
        <h1 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Admin
        </h1>
        <nav className="mt-4 flex flex-col gap-1 text-sm">
          {SECTIONS.map((s) => (
            <Link
              key={s.href}
              href={s.href}
              className="rounded-md px-3 py-2 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {s.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
