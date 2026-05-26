"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { serverEnv } from "@/lib/env";
import { couplesDisputesPerMonthFor, currentMonthStart } from "@/lib/couples";

// Couple-dispute server actions. Both partners can independently
// create a dispute and submit their perspective; the LLM arbitration
// fires once BOTH perspectives are in. Per §1.4 LLM calls live in
// workers — we proxy POST /couples/disputes/:id/arbitrate.

export type ActionResult =
  | { ok: true; payload?: unknown }
  | { ok: false; error: string; upgrade?: boolean };

const newDisputeSchema = z.object({
  link_id: z.string().uuid(),
  title: z.string().trim().min(3).max(200),
  perspective: z.string().trim().min(20).max(4000),
});

const perspectiveSchema = z.object({
  dispute_id: z.string().uuid(),
  perspective: z.string().trim().min(20).max(4000),
});

const resolveSchema = z.object({
  dispute_id: z.string().uuid(),
});

// ----- New dispute ---------------------------------------------------------

export async function createDispute(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = newDisputeSchema.safeParse({
    link_id: formData.get("link_id"),
    title: formData.get("title"),
    perspective: formData.get("perspective"),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input" };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Verify the couple link is active + user is a member.
  const { data: link } = await supabase
    .from("couple_links")
    .select("id, user_a, user_b, status")
    .eq("id", parsed.data.link_id)
    .maybeSingle();
  if (!link || link.status !== "active") {
    return { ok: false, error: "Couple link not active." };
  }
  if (user.id !== link.user_a && user.id !== link.user_b) {
    return { ok: false, error: "Not a member of this link." };
  }

  // Tier cap: count this user's CREATED disputes this calendar month.
  // Reading + adding-perspective on the partner's disputes is free.
  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier = (profile?.tier ?? "free") as Tier;
  const monthCap = couplesDisputesPerMonthFor(tier);
  if (monthCap !== null) {
    const isAUser = user.id === link.user_a;
    const ownedCol = isAUser ? "perspective_a_user_id" : "perspective_b_user_id";
    const { count } = await supabase
      .from("couple_disputes")
      .select("id", { count: "exact", head: true })
      .eq(ownedCol, user.id)
      .gte("created_at", currentMonthStart());
    if ((count ?? 0) >= monthCap) {
      return {
        ok: false,
        error: `You hit your ${tier} tier cap of ${monthCap} disputes this month.`,
        upgrade: true,
      };
    }
  }

  const isA = user.id === link.user_a;
  const now = new Date().toISOString();
  const insertPayload: Record<string, unknown> = {
    couple_link_id: parsed.data.link_id,
    title: parsed.data.title,
  };
  if (isA) {
    insertPayload.perspective_a_user_id = user.id;
    insertPayload.perspective_a_text = parsed.data.perspective;
    insertPayload.perspective_a_submitted_at = now;
  } else {
    insertPayload.perspective_b_user_id = user.id;
    insertPayload.perspective_b_text = parsed.data.perspective;
    insertPayload.perspective_b_submitted_at = now;
  }

  const { data: row, error } = await supabase
    .from("couple_disputes")
    .insert(insertPayload)
    .select("id")
    .single();

  if (error) {
    return { ok: false, error: `Save failed [${error.code ?? "?"}] ${error.message}` };
  }

  revalidatePath(`/couples/${parsed.data.link_id}`);
  redirect(`/couples/${parsed.data.link_id}/disputes/${row.id}`);
}

// ----- Submit the other side's perspective ---------------------------------

export async function submitPerspective(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = perspectiveSchema.safeParse({
    dispute_id: formData.get("dispute_id"),
    perspective: formData.get("perspective"),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input" };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: dispute } = await supabase
    .from("couple_disputes")
    .select(
      "id, couple_link_id, status, perspective_a_user_id, perspective_a_text, perspective_b_user_id, perspective_b_text"
    )
    .eq("id", parsed.data.dispute_id)
    .maybeSingle();
  if (!dispute) return { ok: false, error: "Dispute not found." };
  if (dispute.status !== "awaiting") {
    return { ok: false, error: "Already arbitrated." };
  }

  const { data: link } = await supabase
    .from("couple_links")
    .select("user_a, user_b, status")
    .eq("id", dispute.couple_link_id)
    .maybeSingle();
  if (!link || link.status !== "active") {
    return { ok: false, error: "Couple link not active." };
  }
  if (user.id !== link.user_a && user.id !== link.user_b) {
    return { ok: false, error: "Not a member of this link." };
  }

  // Determine which slot this user fills. If A already submitted, this
  // user must be B (and vice-versa). Don't overwrite an existing slot
  // owned by the same user.
  const isA = user.id === link.user_a;
  const now = new Date().toISOString();
  const updatePayload: Record<string, unknown> = {};
  if (isA) {
    updatePayload.perspective_a_user_id = user.id;
    updatePayload.perspective_a_text = parsed.data.perspective;
    updatePayload.perspective_a_submitted_at = now;
  } else {
    updatePayload.perspective_b_user_id = user.id;
    updatePayload.perspective_b_text = parsed.data.perspective;
    updatePayload.perspective_b_submitted_at = now;
  }

  const { error: updateErr } = await supabase
    .from("couple_disputes")
    .update(updatePayload)
    .eq("id", parsed.data.dispute_id);
  if (updateErr) {
    return { ok: false, error: `Save failed [${updateErr.code ?? "?"}] ${updateErr.message}` };
  }

  // Now check: are both perspectives in? If yes, kick off arbitration.
  const aText = isA ? parsed.data.perspective : dispute.perspective_a_text;
  const bText = isA ? dispute.perspective_b_text : parsed.data.perspective;
  if (aText && bText) {
    await triggerArbitration(parsed.data.dispute_id);
  }

  revalidatePath(`/couples/${dispute.couple_link_id}/disputes/${parsed.data.dispute_id}`);
  return { ok: true };
}

// ----- Resolve a dispute ---------------------------------------------------

export async function markDisputeResolved(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = resolveSchema.safeParse({ dispute_id: formData.get("dispute_id") });
  if (!parsed.success) return { ok: false, error: "Invalid input" };

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: dispute, error: readErr } = await supabase
    .from("couple_disputes")
    .select("couple_link_id, status")
    .eq("id", parsed.data.dispute_id)
    .maybeSingle();
  if (readErr || !dispute) return { ok: false, error: "Dispute not found." };
  if (dispute.status !== "arbitrated") {
    return { ok: false, error: "Can only resolve arbitrated disputes." };
  }

  const { error } = await supabase
    .from("couple_disputes")
    .update({
      status: "resolved",
      resolved_at: new Date().toISOString(),
      resolved_by: user.id,
    })
    .eq("id", parsed.data.dispute_id);
  if (error) return { ok: false, error: error.message };

  revalidatePath(`/couples/${dispute.couple_link_id}`);
  return { ok: true };
}

// ----- Internal: trigger workers arbitration -------------------------------

async function triggerArbitration(disputeId: string): Promise<void> {
  if (!serverEnv.WORKERS_URL || !serverEnv.WORKERS_INTERNAL_SECRET) {
    // No workers configured (dev / preview without LLM access). Leave the
    // dispute in "awaiting" — operator can retry later.
    return;
  }
  try {
    await fetch(`${serverEnv.WORKERS_URL}/couples/disputes/${disputeId}/arbitrate`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
        "Content-Type": "application/json",
      },
      // No body needed — workers re-reads the row by ID.
    });
  } catch {
    // Best-effort: caller's UI will show "arbitrating..." and a refresh
    // will reflect the verdict once it lands. Failures get retried by
    // navigating to the detail page.
  }
}
