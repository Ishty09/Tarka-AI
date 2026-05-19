"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createServerSupabase } from "@/lib/supabase/server";
import {
  moderateFeedPost,
  moderatePersona,
  reviewIncident,
  suspendUser as suspendUserFn,
  unsuspendUser as unsuspendUserFn,
} from "@/lib/admin";

export type ActionResult = { ok: true } | { ok: false; error: string };

async function callerId(): Promise<string> {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  return user.id;
}

export async function approvePersonaAction(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const id = (formData.get("persona_id") ?? "").toString();
  const notes = (formData.get("notes") ?? "").toString().trim() || undefined;
  if (!id) return { ok: false, error: "Missing persona id." };
  const res = await moderatePersona(await callerId(), {
    persona_id: id,
    action: "approve",
    notes,
  });
  if (!res.ok) return { ok: false, error: res.error };
  revalidatePath("/admin/moderation");
  return { ok: true };
}

export async function rejectPersonaAction(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const id = (formData.get("persona_id") ?? "").toString();
  const notes = (formData.get("notes") ?? "").toString().trim() || undefined;
  if (!id) return { ok: false, error: "Missing persona id." };
  const res = await moderatePersona(await callerId(), {
    persona_id: id,
    action: "reject",
    notes,
  });
  if (!res.ok) return { ok: false, error: res.error };
  revalidatePath("/admin/moderation");
  return { ok: true };
}

export async function approveFeedPostAction(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const id = (formData.get("post_id") ?? "").toString();
  const notes = (formData.get("notes") ?? "").toString().trim() || undefined;
  if (!id) return { ok: false, error: "Missing post id." };
  const res = await moderateFeedPost(await callerId(), {
    post_id: id,
    action: "approve",
    notes,
  });
  if (!res.ok) return { ok: false, error: res.error };
  revalidatePath("/admin/moderation");
  return { ok: true };
}

export async function rejectFeedPostAction(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const id = (formData.get("post_id") ?? "").toString();
  const notes = (formData.get("notes") ?? "").toString().trim() || undefined;
  if (!id) return { ok: false, error: "Missing post id." };
  const res = await moderateFeedPost(await callerId(), {
    post_id: id,
    action: "reject",
    notes,
  });
  if (!res.ok) return { ok: false, error: res.error };
  revalidatePath("/admin/moderation");
  return { ok: true };
}

export async function removeFeedPostAction(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const id = (formData.get("post_id") ?? "").toString();
  const notes = (formData.get("notes") ?? "").toString().trim() || undefined;
  if (!id) return { ok: false, error: "Missing post id." };
  const res = await moderateFeedPost(await callerId(), {
    post_id: id,
    action: "remove",
    notes,
  });
  if (!res.ok) return { ok: false, error: res.error };
  revalidatePath("/admin/moderation");
  return { ok: true };
}

export async function suspendUserAction(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const id = (formData.get("user_id") ?? "").toString();
  const reason = (formData.get("reason") ?? "").toString().trim();
  if (!id) return { ok: false, error: "Missing user id." };
  if (reason.length < 3) return { ok: false, error: "Reason is required." };
  const res = await suspendUserFn(await callerId(), { user_id: id, reason });
  if (!res.ok) return { ok: false, error: res.error };
  revalidatePath("/admin/users");
  return { ok: true };
}

export async function unsuspendUserAction(formData: FormData): Promise<void> {
  const id = (formData.get("user_id") ?? "").toString();
  if (!id) return;
  await unsuspendUserFn(await callerId(), { user_id: id });
  revalidatePath("/admin/users");
}

export async function reviewIncidentAction(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const id = Number((formData.get("incident_id") ?? "").toString());
  if (!Number.isFinite(id) || id <= 0) return { ok: false, error: "Missing incident id." };
  const notes = (formData.get("notes") ?? "").toString().trim() || undefined;
  const res = await reviewIncident(await callerId(), { incident_id: id, notes });
  if (!res.ok) return { ok: false, error: res.error };
  revalidatePath("/admin/incidents");
  return { ok: true };
}
