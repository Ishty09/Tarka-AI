import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { SettingsSection } from "../_components/SettingsSection";
import { DataActions } from "./DataActions";
import { ExportHistory, type ExportRow } from "./ExportHistory";

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

  const { data: exports } = await supabase
    .from("data_export_requests")
    .select("id, status, requested_at, ready_at, expires_at, byte_size, error_message")
    .eq("user_id", user.id)
    .order("requested_at", { ascending: false })
    .limit(10);

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

      <SettingsSection
        title="Export history"
        description="The last 10 export requests. Download links arrive by email and expire 7 days after the export is ready."
      >
        <ExportHistory rows={(exports ?? []) as ExportRow[]} />
      </SettingsSection>
    </div>
  );
}
