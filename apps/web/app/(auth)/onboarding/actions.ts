"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { LOCALES } from "@quarrel/shared/constants";
import { hashUserId, trackServer } from "@/lib/analytics";
import { createServerSupabase } from "@/lib/supabase/server";

// Every onboarding write goes through here. Each action:
//   1. Loads the signed-in user (auth.uid()) — redirects to /login if absent.
//   2. Validates input with zod (§1 rule 9).
//   3. Upserts the profile row (step 2 creates it; later steps update it).
//   4. Redirects forward.
// We never reveal DB errors verbatim; messages stay user-readable.

export type ActionResult = { ok: true } | { ok: false; error: string };

// ----- Profile (step 2) ------------------------------------------------------

const USERNAME_RE = /^[a-z0-9_]+$/;
const profileSchema = z.object({
  username: z
    .string()
    .min(3)
    .max(30)
    .regex(USERNAME_RE, "Lowercase letters, numbers, and underscores only"),
  display_name: z.string().min(1).max(60),
});

export async function submitProfile(_prev: ActionResult | null, formData: FormData): Promise<ActionResult> {
  const parsed = profileSchema.safeParse({
    username: (formData.get("username") ?? "").toString().toLowerCase().trim(),
    display_name: (formData.get("display_name") ?? "").toString().trim(),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input" };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { error } = await supabase.from("profiles").upsert(
    { id: user.id, username: parsed.data.username, display_name: parsed.data.display_name },
    { onConflict: "id" },
  );

  if (error) {
    // 23505 unique_violation on username
    if (error.code === "23505") return { ok: false, error: "That username is taken." };
    return { ok: false, error: "Couldn't save your profile. Try again." };
  }
  redirect("/onboarding/locale");
}

// ----- Locale (step 3) -------------------------------------------------------

const localeSchema = z.object({
  locale: z.enum(LOCALES),
  country_code: z.string().length(2).transform((v) => v.toUpperCase()),
  timezone: z.string().min(1).max(64),
});

export async function submitLocale(_prev: ActionResult | null, formData: FormData): Promise<ActionResult> {
  const parsed = localeSchema.safeParse({
    locale: formData.get("locale"),
    country_code: formData.get("country_code"),
    timezone: formData.get("timezone"),
  });
  if (!parsed.success) return { ok: false, error: "Pick a valid locale, country, and timezone." };

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { error } = await supabase
    .from("profiles")
    .update(parsed.data)
    .eq("id", user.id);
  if (error) return { ok: false, error: "Couldn't save locale. Try again." };
  redirect("/onboarding/age");
}

// ----- Age (step 4) ----------------------------------------------------------

const ageSchema = z.object({
  age_range: z.enum(["under_16", "16_17", "18_plus"]),
});

export async function submitAge(_prev: ActionResult | null, formData: FormData): Promise<ActionResult> {
  const parsed = ageSchema.safeParse({ age_range: formData.get("age_range") });
  if (!parsed.success) return { ok: false, error: "Pick an age range." };

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { error } = await supabase
    .from("profiles")
    .update({
      age_range: parsed.data.age_range,
      age_verified_at: new Date().toISOString(),
      age_verification_method: "self_declared",
    })
    .eq("id", user.id);
  if (error) return { ok: false, error: "Couldn't save age. Try again." };
  redirect("/onboarding/intent");
}

// ----- Intent (step 5) -------------------------------------------------------
// Schema gap: no `intents` column. Intent passes through URL params to step 6.

const INTENT_VALUES = [
  "argue",
  "roast",
  "mediate",
  "track",
  "rehearse",
  "explore",
] as const;
const intentSchema = z.object({
  intents: z.array(z.enum(INTENT_VALUES)).min(1).max(3),
});

export async function submitIntent(_prev: ActionResult | null, formData: FormData): Promise<ActionResult> {
  const intents = formData.getAll("intents").map((v) => v.toString());
  const parsed = intentSchema.safeParse({ intents });
  if (!parsed.success) return { ok: false, error: "Pick one to three reasons." };

  const params = new URLSearchParams();
  for (const intent of parsed.data.intents) params.append("intent", intent);
  redirect(`/onboarding/persona?${params.toString()}`);
}

// ----- Persona pick (step 6) -------------------------------------------------
// Schema gap: no installed-personas join table. We forward the slug to the
// rest of the flow via URL params; /chat/new (Phase B) will pick it up.

const personaPickSchema = z.object({
  persona_slug: z.string().min(1).max(80),
});

export async function submitPersonaPick(_prev: ActionResult | null, formData: FormData): Promise<ActionResult> {
  const parsed = personaPickSchema.safeParse({ persona_slug: formData.get("persona_slug") });
  if (!parsed.success) return { ok: false, error: "Pick a persona." };
  // §20 persona_installed — onboarding step 6 "Pick first persona (one-
  // click install)". The schema has no installed-personas join table yet
  // (§4 directory note), so this event is the canonical record of
  // first-time persona selection until that table lands.
  await trackServer("persona_installed", { persona_slug: parsed.data.persona_slug });
  const params = new URLSearchParams({ persona: parsed.data.persona_slug });
  redirect(`/onboarding/daily-roast?${params.toString()}`);
}

// ----- Daily roast (step 7) --------------------------------------------------

const dailyRoastSchema = z
  .object({
    enabled: z.enum(["on", "off"]),
    time: z.string().optional(),
    persona_slug: z.string().min(1).max(80).optional(),
    persona_carry: z.string().optional(),
  })
  .refine((v) => v.enabled !== "on" || (!!v.time && !!v.persona_slug), {
    message: "Pick a time and persona for your daily roast.",
  });

export async function submitDailyRoast(_prev: ActionResult | null, formData: FormData): Promise<ActionResult> {
  const parsed = dailyRoastSchema.safeParse({
    enabled: formData.get("enabled"),
    time: formData.get("time")?.toString() || undefined,
    persona_slug: formData.get("persona_slug")?.toString() || undefined,
    persona_carry: formData.get("persona_carry")?.toString() || undefined,
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Check the inputs." };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const update = parsed.data.enabled === "on"
    ? {
        daily_roast_time: parsed.data.time,
        daily_roast_persona_slug: parsed.data.persona_slug,
        notification_push: true,
      }
    : {
        daily_roast_time: null,
        daily_roast_persona_slug: null,
        notification_push: false,
      };

  const { error } = await supabase.from("profiles").update(update).eq("id", user.id);
  if (error) return { ok: false, error: "Couldn't save daily roast prefs. Try again." };

  const params = parsed.data.persona_carry
    ? new URLSearchParams({ persona: parsed.data.persona_carry }).toString()
    : "";
  redirect(`/onboarding/emergency${params ? `?${params}` : ""}`);
}

// ----- Emergency contact (step 8) --------------------------------------------

const emergencySchema = z
  .object({
    name: z.string().max(120).optional(),
    email: z.string().email().optional().or(z.literal("")),
    skip: z.string().optional(),
    persona_carry: z.string().optional(),
  })
  .refine((v) => v.skip === "true" || (!!v.name && !!v.email), {
    message: "Enter a name and email, or skip.",
  });

export async function submitEmergency(_prev: ActionResult | null, formData: FormData): Promise<ActionResult> {
  const parsed = emergencySchema.safeParse({
    name: formData.get("name")?.toString().trim() || undefined,
    email: formData.get("email")?.toString().trim() || undefined,
    skip: formData.get("skip")?.toString(),
    persona_carry: formData.get("persona_carry")?.toString() || undefined,
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Check the inputs." };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  if (parsed.data.skip !== "true") {
    const { error } = await supabase
      .from("profiles")
      .update({
        emergency_contact_name: parsed.data.name,
        emergency_contact_email: parsed.data.email,
      })
      .eq("id", user.id);
    if (error) return { ok: false, error: "Couldn't save emergency contact. Try again." };
  }

  const params = parsed.data.persona_carry
    ? new URLSearchParams({ persona: parsed.data.persona_carry }).toString()
    : "";
  redirect(`/onboarding/legal${params ? `?${params}` : ""}`);
}

// ----- Legal acceptance (step 9) --------------------------------------------

const legalSchema = z
  .object({
    privacy: z.literal("on"),
    terms: z.literal("on"),
    marketing: z.string().optional(),
    persona_carry: z.string().optional(),
  })
  .transform((v) => ({
    marketing: v.marketing === "on",
    persona_carry: v.persona_carry,
  }));

export async function submitLegal(_prev: ActionResult | null, formData: FormData): Promise<ActionResult> {
  const parsed = legalSchema.safeParse({
    privacy: formData.get("privacy"),
    terms: formData.get("terms"),
    marketing: formData.get("marketing")?.toString(),
    persona_carry: formData.get("persona_carry")?.toString() || undefined,
  });
  if (!parsed.success) {
    return { ok: false, error: "You must accept the Privacy Policy and Terms to continue." };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { error } = await supabase
    .from("profiles")
    .update({
      marketing_email_consent: parsed.data.marketing,
      onboarding_completed_at: new Date().toISOString(),
    })
    .eq("id", user.id);
  if (error) return { ok: false, error: "Couldn't finish onboarding. Try again." };

  await trackServer("onboarding_completed", {
    user_id: hashUserId(user.id),
    marketing_consent: parsed.data.marketing,
  });

  const target = parsed.data.persona_carry
    ? `/chat?persona=${encodeURIComponent(parsed.data.persona_carry)}`
    : "/chat";
  redirect(target);
}
