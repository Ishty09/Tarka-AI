"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

export type ActionResult =
  | { ok: true; payload?: unknown }
  | { ok: false; error: string };

const logSchema = z.object({
  link_id: z.string().uuid(),
  effort_rating: z.coerce.number().int().min(1).max(5),
  partner_appreciation: z.string().trim().max(300).optional(),
  frustration: z.string().trim().max(300).optional(),
});

export async function saveDailyLog(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = logSchema.safeParse({
    link_id: formData.get("link_id"),
    effort_rating: formData.get("effort_rating"),
    partner_appreciation: formData.get("partner_appreciation") || undefined,
    frustration: formData.get("frustration") || undefined,
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input" };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Verify link membership.
  const { data: link } = await supabase
    .from("couple_links")
    .select("user_a, user_b, status")
    .eq("id", parsed.data.link_id)
    .maybeSingle();
  if (!link || link.status !== "active") {
    return { ok: false, error: "Couple link not active." };
  }
  if (user.id !== link.user_a && user.id !== link.user_b) {
    return { ok: false, error: "Not a member of this link." };
  }

  const today = new Date().toISOString().slice(0, 10);

  const { error } = await supabase
    .from("couple_health_logs")
    .upsert(
      {
        couple_link_id: parsed.data.link_id,
        user_id: user.id,
        log_date: today,
        effort_rating: parsed.data.effort_rating,
        partner_appreciation: parsed.data.partner_appreciation ?? null,
        frustration: parsed.data.frustration ?? null,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "couple_link_id,user_id,log_date" },
    );
  if (error) {
    return { ok: false, error: `Save failed [${error.code ?? "?"}] ${error.message}` };
  }

  revalidatePath(`/couples/${parsed.data.link_id}/health`);
  return { ok: true };
}
