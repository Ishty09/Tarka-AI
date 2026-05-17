import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

// Persona library. RLS gives us three buckets in one query:
//   - "Official"  — visibility in ('official') + approved  (Quarrel-built)
//   - "Community" — visibility='public' + approved + owned by someone else
//   - "Yours"     — owner_id = auth.uid() (any visibility / status)
// We split client-side so the user sees their drafts (pending moderation)
// alongside the polished options.

type CategoryFilter =
  | "all"
  | "argue"
  | "roast"
  | "mediate"
  | "council"
  | "productivity"
  | "cultural";

const CATEGORIES: { value: CategoryFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "argue", label: "Argue" },
  { value: "roast", label: "Roast" },
  { value: "mediate", label: "Mediate" },
  { value: "council", label: "Council" },
  { value: "productivity", label: "Productivity" },
  { value: "cultural", label: "Cultural" },
];

interface PageProps {
  searchParams: Promise<{ category?: string }>;
}

export default async function PersonasPage({ searchParams }: PageProps) {
  const { category: categoryParam } = await searchParams;
  const category: CategoryFilter = isCategoryFilter(categoryParam) ? categoryParam : "all";

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  let query = supabase
    .from("personas")
    .select("id, slug, name, description, category, visibility, moderation_status, owner_id, locale, rating_avg, install_count")
    .order("install_count", { ascending: false });

  if (category !== "all") query = query.eq("category", category);

  const { data: personas } = await query;

  const official: typeof personas = [];
  const community: typeof personas = [];
  const yours: typeof personas = [];
  for (const p of personas ?? []) {
    if (p.owner_id === user.id) yours.push(p);
    else if (p.visibility === "official") official.push(p);
    else community.push(p);
  }

  return (
    <main className="mx-auto w-full max-w-5xl p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Personas</h1>
        <Link
          href="/personas/create"
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          Create
        </Link>
      </div>

      <nav className="mt-4 flex flex-wrap gap-2">
        {CATEGORIES.map((c) => {
          const active = c.value === category;
          return (
            <Link
              key={c.value}
              href={c.value === "all" ? "/personas" : `/personas?category=${c.value}`}
              className={`rounded-full border px-3 py-1 text-xs ${
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input bg-background hover:bg-accent"
              }`}
            >
              {c.label}
            </Link>
          );
        })}
      </nav>

      <Section title="Official" personas={official} />
      <Section title="Your personas" personas={yours} emptyHint="You haven't created any yet." />
      <Section title="Community" personas={community} emptyHint="No community personas approved yet." />
    </main>
  );
}

function isCategoryFilter(v: string | undefined): v is CategoryFilter {
  return v === "all" || v === "argue" || v === "roast" || v === "mediate"
    || v === "council" || v === "productivity" || v === "cultural";
}

function Section({
  title,
  personas,
  emptyHint,
}: {
  title: string;
  personas: Array<{
    id: string;
    slug: string;
    name: string;
    description: string | null;
    category: string;
    visibility: string;
    moderation_status: string;
    rating_avg: number | null;
    install_count: number;
  }> | null | undefined;
  emptyHint?: string;
}) {
  if (!personas || personas.length === 0) {
    if (!emptyHint) return null;
    return (
      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{emptyHint}</p>
      </section>
    );
  }

  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {personas.map((p) => (
          <li key={p.id}>
            <Link
              href={`/personas/${p.slug}`}
              className="flex h-full flex-col gap-2 rounded-md border border-input bg-background p-4 shadow-sm hover:bg-accent"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{p.name}</span>
                <span className="text-xs uppercase tracking-wide text-muted-foreground">{p.category}</span>
              </div>
              {p.description && (
                <p className="line-clamp-3 text-sm text-muted-foreground">{p.description}</p>
              )}
              <div className="mt-auto flex items-center gap-2 text-xs text-muted-foreground">
                {p.moderation_status !== "approved" && (
                  <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-700">
                    {p.moderation_status}
                  </span>
                )}
                <span>{p.install_count} installs</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
