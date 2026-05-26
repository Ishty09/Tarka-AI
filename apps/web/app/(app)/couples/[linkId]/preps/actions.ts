"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { serverEnv } from "@/lib/env";
import { couplesPrepsPerMonthFor, currentMonthStart } from "@/lib/couples";

export type ActionResult =
  | { ok: true; payload?: { id?: string } }
  | { ok: false; error: string };

const createSchema = z.object({
  link_id: z.string().uuid(),
  topic: z.string().trim().min(5).max(200),
  desired_outcome: z.string().trim().max(500).optional(),
  context: z.string().trim().max(2000).optional(),
});

export async function createPrep(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = createSchema.safeParse({
    link_id: formData.get("link_id"),
    topic: formData.get("topic"),
    desired_outcome: formData.get("desired_outcome") || undefined,
    context: formData.get("context") || undefined,
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input" };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

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

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier = (profile?.tier ?? "free") as Tier;
  const monthCap = couplesPrepsPerMonthFor(tier);
  if (monthCap !== null) {
    const { count } = await supabase
      .from("couple_conversation_preps")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id)
      .gte("created_at", currentMonthStart());
    if ((count ?? 0) >= monthCap) {
      return {
        ok: false,
        error: `You hit your ${tier} tier cap of ${monthCap} preps this month. Upgrade for more.`,
      };
    }
  }

  const { data: row, error } = await supabase
    .from("couple_conversation_preps")
    .insert({
      couple_link_id: parsed.data.link_id,
      user_id: user.id,
      topic: parsed.data.topic,
      desired_outcome: parsed.data.desired_outcome ?? null,
      context: parsed.data.context ?? null,
    })
    .select("id")
    .single();

  if (error || !row) {
    return { ok: false, error: error?.message ?? "Save failed" };
  }

  // Fire generation in workers. Best-effort — if it fails, the prep
  // sits in "pending" and the user can manually retry from the page.
  if (serverEnv.WORKERS_URL && serverEnv.WORKERS_INTERNAL_SECRET) {
    try {
      await fetch(
        `${serverEnv.WORKERS_URL}/couples/preps/${row.id}/generate`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
            "Content-Type": "application/json",
          },
        },
      );
    } catch {
      /* status reflected via row */
    }
  }

  revalidatePath(`/couples/${parsed.data.link_id}/preps`);
  redirect(`/couples/${parsed.data.link_id}/preps/${row.id}`);
}
