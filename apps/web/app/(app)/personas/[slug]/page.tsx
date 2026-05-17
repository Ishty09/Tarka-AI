import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

// Single-persona detail. Shows enough information for the user to decide
// whether to start a chat with it. The system prompt is exposed only for
// the owner — official/community prompts stay private to keep the "voice"
// from being trivially copied (§10.2 marketplace economics).

interface PageProps {
  params: Promise<{ slug: string }>;
}

const CATEGORY_TO_MODE: Record<string, string> = {
  argue: "argue",
  roast: "roast",
  mediate: "mediate",
  council: "council",
  productivity: "custom",
  cultural: "argue",
};

export default async function PersonaDetailPage({ params }: PageProps) {
  const { slug } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: persona } = await supabase
    .from("personas")
    .select("id, slug, name, description, category, locale, cultural_tag, visibility, moderation_status, owner_id, system_prompt, install_count, rating_avg, rating_count")
    .eq("slug", slug)
    .maybeSingle();

  if (!persona) notFound();

  const isOwner = persona.owner_id === user.id;
  const mode = CATEGORY_TO_MODE[persona.category] ?? "custom";
  const startable = persona.moderation_status === "approved" || isOwner;

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <Link href="/personas" className="text-sm text-muted-foreground hover:underline">
        ← Personas
      </Link>

      <div className="mt-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{persona.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span className="capitalize">{persona.category}</span>
            <span>·</span>
            <span>{persona.locale}</span>
            {persona.cultural_tag && <><span>·</span><span>{persona.cultural_tag}</span></>}
            <span>·</span>
            <span>{persona.install_count} installs</span>
            {persona.moderation_status !== "approved" && (
              <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-700">
                {persona.moderation_status}
              </span>
            )}
          </div>
        </div>
        {startable ? (
          <Link
            href={`/chat/new?persona=${persona.slug}&mode=${mode}`}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            Start chat
          </Link>
        ) : (
          <span className="rounded-md border border-input bg-background px-3 py-2 text-xs text-muted-foreground">
            Awaiting moderation
          </span>
        )}
      </div>

      {persona.description && (
        <p className="mt-6 text-sm leading-relaxed">{persona.description}</p>
      )}

      {isOwner && (
        <section className="mt-8">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            System prompt (visible to you only)
          </h2>
          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-input bg-muted/30 p-3 text-xs">
            {persona.system_prompt}
          </pre>
        </section>
      )}
    </main>
  );
}
