import { OnboardingShell } from "../_components/Shell";
import { DailyRoastForm } from "./DailyRoastForm";
import { createServerSupabase } from "@/lib/supabase/server";

interface PageProps {
  searchParams: Promise<{ persona?: string }>;
}

export default async function DailyRoastPage({ searchParams }: PageProps) {
  const { persona } = await searchParams;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  const { data: profile } = user
    ? await supabase.from("profiles").select("locale").eq("id", user.id).maybeSingle()
    : { data: null };
  const locale = profile?.locale ?? "en";

  const { data: roastPersonas } = await supabase
    .from("personas")
    .select("slug, name")
    .eq("visibility", "official")
    .eq("moderation_status", "approved")
    .in("category", ["roast", "cultural"])
    .eq("locale", locale)
    .limit(10);

  // Fall back to the persona picked in step 6 if nothing in roast category.
  const personas = roastPersonas && roastPersonas.length > 0
    ? roastPersonas
    : persona ? [{ slug: persona, name: persona }] : [];

  return (
    <OnboardingShell
      step="daily-roast"
      title="Daily roast?"
      subline="One push notification a day, at a time you pick. You can turn it off here."
    >
      <DailyRoastForm personas={personas} personaCarry={persona ?? ""} />
    </OnboardingShell>
  );
}
