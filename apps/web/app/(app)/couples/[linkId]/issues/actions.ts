"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

export type ActionResult =
  | { ok: true; payload?: unknown }
  | { ok: false; error: string };

const STATUSES = ["discussed", "agreed", "resolved", "recurring"] as const;

const createSchema = z.object({
  link_id: z.string().uuid(),
  theme: z.string().trim().min(2).max(100),
  description: z.string().trim().max(1000).optional(),
  severity: z.coerce.number().int().min(1).max(10).optional(),
});

const updateStatusSchema = z.object({
  issue_id: z.string().uuid(),
  status: z.enum(STATUSES),
  notes: z.string().trim().max(1000).optional(),
});

export async function createIssue(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = createSchema.safeParse({
    link_id: formData.get("link_id"),
    theme: formData.get("theme"),
    description: formData.get("description") || undefined,
    severity: formData.get("severity") || undefined,
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

  const { error } = await supabase.from("couple_issues").insert({
    couple_link_id: parsed.data.link_id,
    theme: parsed.data.theme,
    description: parsed.data.description ?? null,
    severity: parsed.data.severity ?? 5,
    source: "manual",
    created_by: user.id,
  });
  if (error) {
    return { ok: false, error: `Save failed [${error.code ?? "?"}] ${error.message}` };
  }

  revalidatePath(`/couples/${parsed.data.link_id}/issues`);
  return { ok: true };
}

export async function updateIssueStatus(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = updateStatusSchema.safeParse({
    issue_id: formData.get("issue_id"),
    status: formData.get("status"),
    notes: formData.get("notes") || undefined,
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input" };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: issue } = await supabase
    .from("couple_issues")
    .select("couple_link_id, status")
    .eq("id", parsed.data.issue_id)
    .maybeSingle();
  if (!issue) return { ok: false, error: "Issue not found." };

  const now = new Date().toISOString();
  const updatePayload: Record<string, unknown> = {
    status: parsed.data.status,
    last_discussed_at: now,
    updated_at: now,
  };
  if (parsed.data.notes) updatePayload.notes = parsed.data.notes;
  if (parsed.data.status === "resolved") {
    updatePayload.resolved_at = now;
    updatePayload.resolved_by = user.id;
  }

  const { error } = await supabase
    .from("couple_issues")
    .update(updatePayload)
    .eq("id", parsed.data.issue_id);
  if (error) return { ok: false, error: error.message };

  revalidatePath(`/couples/${issue.couple_link_id}/issues`);
  return { ok: true };
}
