import { OnboardingShell } from "../_components/Shell";
import { LocaleForm } from "./LocaleForm";
import { createServerSupabase } from "@/lib/supabase/server";

export default async function LocalePage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  const { data: profile } = user
    ? await supabase.from("profiles").select("locale, country_code, timezone").eq("id", user.id).maybeSingle()
    : { data: null };

  return (
    <OnboardingShell
      step="locale"
      title="Where are you?"
      subline="We use this for cultural personas and crisis hotlines."
    >
      <LocaleForm
        defaultLocale={profile?.locale ?? "en"}
        defaultCountry={profile?.country_code ?? "US"}
        defaultTimezone={profile?.timezone ?? "UTC"}
      />
    </OnboardingShell>
  );
}
