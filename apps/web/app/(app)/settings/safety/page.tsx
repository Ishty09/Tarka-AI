import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { SettingsSection } from "../_components/SettingsSection";
import { EmergencyContactForm } from "./EmergencyContactForm";

// §12.6 — Safety. Emergency contact + crisis hotline preview for the user's
// locale + country. Block list is on the backlog (needs a `user_blocks`
// table — schema change deferred per CLAUDE.md §1.13).

type Hotline = {
  name: string;
  phone: string | null;
  url: string | null;
  context_tag: string;
};

export default async function SafetyPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select(
      "emergency_contact_name, emergency_contact_email, locale, country_code",
    )
    .eq("id", user.id)
    .maybeSingle();
  if (!profile) redirect("/onboarding");

  const { data: hotlinesRaw } = await supabase
    .from("crisis_hotlines")
    .select("name, phone, url, context_tag")
    .eq("locale", profile.locale)
    .eq("country_code", profile.country_code);
  const hotlines = (hotlinesRaw ?? []) as Hotline[];

  return (
    <div className="flex flex-col gap-6">
      <SettingsSection
        title="Emergency contact"
        description="Triggered only by repeated crisis signals — not by an angry chat."
      >
        <EmergencyContactForm
          initial={{
            name: profile.emergency_contact_name ?? "",
            email: profile.emergency_contact_email ?? "",
          }}
        />
      </SettingsSection>

      <SettingsSection
        title={`Crisis hotlines — ${profile.country_code} (${profile.locale})`}
        description="If you ever want them. Change locale or country on the Profile page."
      >
        {hotlines.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No region-matched hotlines yet. International directory:{" "}
            <a
              href="https://blog.opencounseling.com/suicide-hotlines/"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              befrienders / IASP
            </a>
          </p>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {hotlines.map((h) => (
              <li
                key={`${h.name}-${h.context_tag}`}
                className="flex items-center justify-between gap-3 rounded-md border border-input px-3 py-2"
              >
                <div>
                  <p className="font-medium">{h.name}</p>
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    {h.context_tag}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1 text-xs">
                  {h.phone && <span className="font-medium">{h.phone}</span>}
                  {h.url && (
                    <a
                      href={h.url}
                      target="_blank"
                      rel="noreferrer"
                      className="underline text-muted-foreground"
                    >
                      Open →
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </SettingsSection>
    </div>
  );
}
