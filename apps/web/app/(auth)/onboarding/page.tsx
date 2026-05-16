import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { ONBOARDING_PATH, nextOnboardingStep } from "@/lib/onboarding";

// Resume entry-point. Authenticated users hit /onboarding and are bounced to
// the first step they haven't completed (or /chat if onboarding is done).

export default async function OnboardingRootPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login?next=/onboarding");

  const { data: profile } = await supabase
    .from("profiles")
    .select("*")
    .eq("id", user.id)
    .maybeSingle();

  const step = nextOnboardingStep(profile);
  if (step === "done") redirect("/chat");
  redirect(ONBOARDING_PATH[step]);
}
