import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { SettingsSection } from "./_components/SettingsSection";
import { ProfileForm } from "./ProfileForm";

// §12.1 — Profile. Username is read-only (CLAUDE.md mentions a 30-day cooldown
// for renames; we don't track username_changed_at yet so we punt to support).

export default async function ProfilePage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("username, display_name, avatar_url, locale, country_code, timezone")
    .eq("id", user.id)
    .maybeSingle();
  if (!profile) redirect("/onboarding");

  return (
    <div className="flex flex-col gap-6">
      <SettingsSection
        title="Profile"
        description="How Quarrel addresses you and where it places you."
      >
        <ProfileForm
          initial={{
            username: profile.username,
            display_name: profile.display_name ?? "",
            avatar_url: profile.avatar_url ?? "",
            locale: profile.locale,
            country_code: profile.country_code,
            timezone: profile.timezone,
          }}
        />
      </SettingsSection>
    </div>
  );
}
