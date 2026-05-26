import { redirect } from "next/navigation";
import {
  type NotificationPreferences,
} from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { SettingsSection } from "../_components/SettingsSection";
import { NotificationsForm } from "./NotificationsForm";

// §12.2 — Notifications. Global push/email toggles act as master
// overrides; the per-category toggles (notification_preferences) let
// users mute a topic without losing transactional / security email.

export default async function NotificationsPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const [{ data: profile }, { data: personas }] = await Promise.all([
    supabase
      .from("profiles")
      .select(
        "notification_email, notification_push, marketing_email_consent, daily_roast_time, daily_roast_persona_slug, locale, notification_preferences",
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

  const prefs = (profile.notification_preferences ?? {}) as NotificationPreferences;

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
            preferences: prefs,
          }}
          personas={personaOptions}
        />
      </SettingsSection>
    </div>
  );
}
