import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { SettingsSection } from "../_components/SettingsSection";
import { NotificationsForm } from "./NotificationsForm";

// §12.2 — Notifications. Per-event toggles (contradiction surfaced, couples
// invite, wager check-in, mirror ready, eulogy ready, marketing) are
// represented today by the global email/push toggles + marketing consent +
// Daily Roast on/off; finer-grained per-event toggles arrive with the
// notification_preferences column (deferred — needs a migration).

export default async function NotificationsPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const [{ data: profile }, { data: personas }] = await Promise.all([
    supabase
      .from("profiles")
      .select(
        "notification_email, notification_push, marketing_email_consent, daily_roast_time, daily_roast_persona_slug, locale",
      )
      .eq("id", user.id)
      .maybeSingle(),
    supabase
      .from("personas")
      .select("slug, name, locale, visibility, category, moderation_status")
      .in("visibility", ["official", "public"])
      .eq("moderation_status", "approved")
      .in("category", ["roast", "cultural"])
      .order("install_count", { ascending: false })
      .limit(40),
  ]);

  if (!profile) redirect("/onboarding");

  // Surface roast/cultural personas, preferring the user's locale first.
  const all = (personas ?? []) as { slug: string; name: string; locale: string }[];
  const preferred = all.filter((p) => p.locale === profile.locale);
  const rest = all.filter((p) => p.locale !== profile.locale);
  const personaOptions = [...preferred, ...rest].map((p) => ({ slug: p.slug, name: p.name }));

  return (
    <div className="flex flex-col gap-6">
      <SettingsSection
        title="Notifications"
        description="How and when Quarrel pings you."
      >
        <NotificationsForm
          initial={{
            notification_email: profile.notification_email,
            notification_push: profile.notification_push,
            marketing_email_consent: profile.marketing_email_consent,
            daily_roast_time: profile.daily_roast_time ?? "",
            daily_roast_persona_slug: profile.daily_roast_persona_slug ?? "",
          }}
          personas={personaOptions}
        />
      </SettingsSection>
    </div>
  );
}
