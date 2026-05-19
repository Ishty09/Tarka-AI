import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { SettingsSection } from "../_components/SettingsSection";
import { DataActions } from "./DataActions";

// §12.5 — Data. Export and account deletion. Per-category deletion (just
// messages, just facts, etc.) is on the backlog — for now full deletion
// covers the GDPR right-to-erasure path on a 30-day grace.

export default async function DataPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("username, data_deletion_requested_at")
    .eq("id", user.id)
    .maybeSingle();
  if (!profile) redirect("/onboarding");

  return (
    <div className="flex flex-col gap-6">
      <SettingsSection
        title="Your data"
        description="Take a copy, or take everything down."
      >
        <DataActions
          username={profile.username}
          deletionRequestedAt={profile.data_deletion_requested_at}
        />
      </SettingsSection>
    </div>
  );
}
