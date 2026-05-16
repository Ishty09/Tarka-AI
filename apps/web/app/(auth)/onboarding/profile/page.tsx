import { OnboardingShell } from "../_components/Shell";
import { ProfileForm } from "./ProfileForm";
import { createServerSupabase } from "@/lib/supabase/server";

export default async function ProfilePage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  const { data: profile } = user
    ? await supabase.from("profiles").select("username, display_name").eq("id", user.id).maybeSingle()
    : { data: null };

  return (
    <OnboardingShell
      step="profile"
      title="Pick a handle"
      subline="Lowercase, numbers, and underscores. Change it later if you regret it."
    >
      <ProfileForm
        defaultUsername={profile?.username ?? ""}
        defaultDisplayName={profile?.display_name ?? user?.user_metadata?.full_name ?? ""}
      />
    </OnboardingShell>
  );
}
