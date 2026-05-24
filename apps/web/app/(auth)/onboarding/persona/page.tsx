import { OnboardingShell } from "../_components/Shell";
import { PersonaPicker } from "./PersonaPicker";
import { createServerSupabase } from "@/lib/supabase/server";

const INTENT_TO_CATEGORY: Record<string, string[]> = {
  argue: ["argue", "council"],
  roast: ["roast", "cultural"],
  mediate: ["mediate"],
  track: ["productivity"],
  rehearse: ["argue", "productivity"],
  explore: ["argue", "roast", "mediate", "cultural"],
};

interface PageProps {
  searchParams: Promise<{ intent?: string | string[] }>;
}

export default async function PersonaPage({ searchParams }: PageProps) {
  const { intent } = await searchParams;
  const intents = Array.isArray(intent) ? intent : intent ? [intent] : [];
  const categories = Array.from(
    new Set(intents.flatMap((i) => INTENT_TO_CATEGORY[i] ?? [])),
  );

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  const { data: profile } = user
    ? await supabase.from("profiles").select("locale").eq("id", user.id).maybeSingle()
    : { data: null };
  const locale = profile?.locale ?? "en";

  // Public personas in user's locale matching the suggested categories; fall
  // back to any locale if too few matches. Limit 6 per §11 step 6.
  let query = supabase
    .from("personas")
    .select("slug, name, description, category, locale")
    .eq("visibility", "official")
    .eq("moderation_status", "approved")
    .limit(6);

  if (categories.length > 0) query = query.in("category", categories);

  const { data: localePersonas } = await query.eq("locale", locale);
  const personas = [...(localePersonas ?? [])];

  if (personas.length < 6) {
    const { data: fallback } = await query;
    const seen = new Set(personas.map((p) => p.slug));
    for (const p of fallback ?? []) {
      if (!seen.has(p.slug) && personas.length < 6) personas.push(p);
    }
  }

  return (
    <OnboardingShell
      step="persona"
      title="Pick your first persona"
      subline="You can install more, create your own, and switch any time."
    >
      <PersonaPicker personas={personas} />
    </OnboardingShell>
  );
}
