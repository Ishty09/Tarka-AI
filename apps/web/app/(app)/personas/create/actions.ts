"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { PERSONA_SYSTEM_PROMPT_MAX_CHARS, LOCALES } from "@quarrel/shared/constants";
import { personaCategorySchema } from "@quarrel/shared/schemas";
import { createServerSupabase } from "@/lib/supabase/server";

// User-created persona insert (§10.2).
//
// Inserts with moderation_status='pending', visibility='private'. Workers
// auto-moderation (§10.2 — quarrel-cheap classifier) is a separate pass
// not wired in this step. Until it lands, owner can use the persona right
// away (RLS personas_owner policy returns it regardless of moderation
// status), but it stays invisible to other users.

export type ActionResult = { ok: true } | { ok: false; error: string };

const createSchema = z.object({
  name: z.string().min(2).max(60),
  description: z.string().min(10).max(500),
  category: personaCategorySchema,
  locale: z.enum(LOCALES),
  system_prompt: z.string().min(50).max(PERSONA_SYSTEM_PROMPT_MAX_CHARS),
});

export async function createPersona(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = createSchema.safeParse({
    name: (formData.get("name") ?? "").toString().trim(),
    description: (formData.get("description") ?? "").toString().trim(),
    category: formData.get("category"),
    locale: formData.get("locale"),
    system_prompt: (formData.get("system_prompt") ?? "").toString(),
  });
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    return { ok: false, error: issue ? `${issue.path.join(".")}: ${issue.message}` : "Invalid input." };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Slug is name-derived plus a short suffix to dodge collisions. Worker
  // doesn't trust this — it's the unique key the user types into URLs.
  const slug = makeSlug(parsed.data.name, user.id);

  const { error } = await supabase.from("personas").insert({
    slug,
    owner_id: user.id,
    name: parsed.data.name,
    description: parsed.data.description,
    locale: parsed.data.locale,
    category: parsed.data.category,
    system_prompt: parsed.data.system_prompt,
    visibility: "private",
    moderation_status: "pending",
  });

  if (error) {
    if (error.code === "23505") {
      return { ok: false, error: "A persona with a similar name already exists. Try a more specific name." };
    }
    return { ok: false, error: "Couldn't create persona. Try again." };
  }

  redirect(`/personas/${slug}`);
}

function makeSlug(name: string, userId: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40);
  const suffix = userId.slice(0, 6);
  return base ? `${base}_${suffix}` : `persona_${suffix}_${Date.now().toString(36)}`;
}
