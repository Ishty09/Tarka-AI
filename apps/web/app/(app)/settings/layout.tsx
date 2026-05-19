import Link from "next/link";

// Side-nav shell for /settings/*. The (app)/layout already enforces auth and
// onboarding completion, so this layout just renders the per-section
// navigation. Settings are split per §12 into six independent surfaces — we
// keep them as sibling routes (not tabs) so each can have its own loading
// state and its server action revalidates only its own slice.

const SECTIONS: { href: string; label: string }[] = [
  { href: "/settings", label: "Profile" },
  { href: "/settings/notifications", label: "Notifications" },
  { href: "/settings/privacy", label: "Privacy" },
  { href: "/settings/billing", label: "Billing" },
  { href: "/settings/data", label: "Data" },
  { href: "/settings/safety", label: "Safety" },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-5xl gap-8 p-6">
      <aside className="w-48 shrink-0">
        <h1 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Settings
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
