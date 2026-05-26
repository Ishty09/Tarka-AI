"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  LOCALES,
  NOTIFICATION_CATEGORIES,
  type Locale,
  type NotificationPreferences,
} from "@quarrel/shared/constants";
import { hashUserId, trackServer } from "@/lib/analytics";
import { createServerSupabase } from "@/lib/supabase/server";

// Server actions for /settings/* pages. Every mutation runs as the signed-in
// user via the cookie-bound Supabase client; RLS (§6.7) enforces ownership
// from the database side. The service-role key NEVER lives in apps/web.

export type ActionResult = { ok: true } | { ok: false; error: string };

// ----- §12.1 Profile ---------------------------------------------------------

const profileSchema = z.object({
  display_name: z
    .string()
    .trim()
    .min(1, "Display name is required.")
    .max(60, "Display name is too long."),
  avatar_url: z
    .string()
    .trim()
    .url("Avatar must be a URL.")
    .max(500)
    .or(z.literal(""))
    .optional(),
  locale: z.enum(LOCALES, { message: "Pick a supported locale." }),
  country_code: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^[A-Z]{2}$/, "Country must be an ISO-3166 alpha-2 code (e.g. US)."),
  timezone: z
    .string()
    .trim()
    .min(2)
    .max(64, "Timezone is too long."),
});

export async function updateProfile(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = profileSchema.safeParse({
    display_name: (formData.get("display_name") ?? "").toString(),
    avatar_url: (formData.get("avatar_url") ?? "").toString(),
    locale: (formData.get("locale") ?? "").toString() as Locale,
    country_code: (formData.get("country_code") ?? "").toString(),
    timezone: (formData.get("timezone") ?? "").toString(),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input." };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { error } = await supabase
    .from("profiles")
    .update({
      display_name: parsed.data.display_name,
      avatar_url: parsed.data.avatar_url || null,
      locale: parsed.data.locale,
      country_code: parsed.data.country_code,
      timezone: parsed.data.timezone,
    })
    .eq("id", user.id);
  if (error) return { ok: false, error: "Couldn't save profile." };

  revalidatePath("/settings");
  return { ok: true };
}

// ----- §12.2 Notifications ---------------------------------------------------

const notificationsSchema = z.object({
  notification_email: z.coerce.boolean(),
  notification_push: z.coerce.boolean(),
  marketing_email_consent: z.coerce.boolean(),
  daily_roast_enabled: z.coerce.boolean(),
  daily_roast_time: z
    .string()
    .trim()
    .regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Use 24h HH:MM.")
    .optional()
    .or(z.literal("")),
  daily_roast_persona_slug: z.string().trim().max(80).optional().or(z.literal("")),
});

export async function updateNotifications(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = notificationsSchema.safeParse({
    notification_email: formData.get("notification_email") === "on",
    notification_push: formData.get("notification_push") === "on",
    marketing_email_consent: formData.get("marketing_email_consent") === "on",
    daily_roast_enabled: formData.get("daily_roast_enabled") === "on",
    daily_roast_time: (formData.get("daily_roast_time") ?? "").toString(),
    daily_roast_persona_slug: (formData.get("daily_roast_persona_slug") ?? "").toString(),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input." };
  }

  // Daily Roast columns are nullable in profiles; clearing them means "off".
  const dailyOn = parsed.data.daily_roast_enabled;
  const time = dailyOn ? (parsed.data.daily_roast_time || null) : null;
  const slug = dailyOn ? (parsed.data.daily_roast_persona_slug || null) : null;

  // Per-category prefs: each pref_<category> checkbox is "on" when allowed
  // and absent when muted. We store muted categories as { push: false,
  // email: false } and OMIT enabled ones so the JSON stays small and the
  // default-allow contract is obvious.
  const preferences: NotificationPreferences = {};
  for (const cat of NOTIFICATION_CATEGORIES) {
    const muted = formData.get(`pref_${cat}`) !== "on";
    if (muted) {
      preferences.push = { ...preferences.push, [cat]: false };
      preferences.email = { ...preferences.email, [cat]: false };
    }
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { error } = await supabase
    .from("profiles")
    .update({
      notification_email: parsed.data.notification_email,
      notification_push: parsed.data.notification_push,
      marketing_email_consent: parsed.data.marketing_email_consent,
      daily_roast_time: time,
      daily_roast_persona_slug: slug,
      notification_preferences: preferences,
    })
    .eq("id", user.id);
  if (error) return { ok: false, error: "Couldn't save notification preferences." };

  revalidatePath("/settings/notifications");
  return { ok: true };
}

// ----- §12.3 Privacy: per-couple cross-fact toggle ---------------------------

const crossFactSchema = z.object({
  couple_link_id: z.string().uuid(),
  enabled: z.coerce.boolean(),
});

export async function setCoupleCrossFactConsent(formData: FormData): Promise<void> {
  const parsed = crossFactSchema.safeParse({
    couple_link_id: (formData.get("couple_link_id") ?? "").toString(),
    enabled: formData.get("enabled") === "on",
  });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Load to determine which slot (user_a / user_b) is mine.
  const { data: link } = await supabase
    .from("couple_links")
    .select("id, user_a, user_b, status")
    .eq("id", parsed.data.couple_link_id)
    .maybeSingle();
  if (!link || link.status !== "active") return;

  const update: Record<string, boolean> =
    link.user_a === user.id
      ? { cross_fact_consent_a: parsed.data.enabled }
      : link.user_b === user.id
        ? { cross_fact_consent_b: parsed.data.enabled }
        : {};
  if (Object.keys(update).length === 0) return;

  await supabase.from("couple_links").update(update).eq("id", link.id);
  revalidatePath("/settings/privacy");
}

// ----- §12.5 Data: export + deletion -----------------------------------------

export async function requestDataExport(): Promise<ActionResult> {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Throttle: only one in-flight (pending/processing) request per user.
  // The worker drains the queue; until it picks up the existing row we
  // don't need to queue another. The owner-insert RLS policy makes the
  // insert itself safe, but the throttle saves operator pages from
  // accidental double-clicks.
  const { data: existing } = await supabase
    .from("data_export_requests")
    .select("id, status")
    .eq("user_id", user.id)
    .in("status", ["pending", "processing"])
    .limit(1)
    .maybeSingle();
  if (existing) {
    return { ok: false, error: "An export is already queued. Watch your inbox." };
  }

  const { error } = await supabase
    .from("data_export_requests")
    .insert({ user_id: user.id });
  if (error) return { ok: false, error: "Couldn't queue export." };

  await trackServer("data_export_requested", { user_id: hashUserId(user.id) });
  revalidatePath("/settings/data");
  return { ok: true };
}

export async function requestAccountDeletion(): Promise<ActionResult> {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { error } = await supabase
    .from("profiles")
    .update({ data_deletion_requested_at: new Date().toISOString() })
    .eq("id", user.id);
  if (error) return { ok: false, error: "Couldn't queue deletion." };

  await trackServer("account_deletion_requested", { user_id: hashUserId(user.id) });
  revalidatePath("/settings/data");
  return { ok: true };
}

export async function cancelAccountDeletion(): Promise<ActionResult> {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { error } = await supabase
    .from("profiles")
    .update({ data_deletion_requested_at: null })
    .eq("id", user.id);
  if (error) return { ok: false, error: "Couldn't cancel deletion." };

  revalidatePath("/settings/data");
  return { ok: true };
}

// ----- §12.6 Safety: emergency contact ---------------------------------------

const emergencySchema = z.object({
  emergency_contact_name: z.string().trim().max(120).optional().or(z.literal("")),
  emergency_contact_email: z
    .string()
    .trim()
    .max(254)
    .email("Enter a valid email.")
    .or(z.literal(""))
    .optional(),
});

export async function updateEmergencyContact(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = emergencySchema.safeParse({
    emergency_contact_name: (formData.get("emergency_contact_name") ?? "").toString(),
    emergency_contact_email: (formData.get("emergency_contact_email") ?? "").toString(),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input." };
  }

  // Both empty means clear; one without the other is invalid because the
  // emergency contact flow needs both a name to address and an email to send
  // to (§9 — emergency_contact_notification).
  const name = parsed.data.emergency_contact_name?.trim() ?? "";
  const email = parsed.data.emergency_contact_email?.trim() ?? "";
  if ((name === "" && email !== "") || (name !== "" && email === "")) {
    return { ok: false, error: "Provide both name and email, or clear both." };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { error } = await supabase
    .from("profiles")
    .update({
      emergency_contact_name: name === "" ? null : name,
      emergency_contact_email: email === "" ? null : email,
    })
    .eq("id", user.id);
  if (error) return { ok: false, error: "Couldn't save emergency contact." };

  revalidatePath("/settings/safety");
  return { ok: true };
}
