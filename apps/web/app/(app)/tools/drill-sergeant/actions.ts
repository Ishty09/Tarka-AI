"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { TIER_LIMITS, type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";

export type ActionResult = { ok: true; payload?: unknown } | { ok: false; error: string };

// ----- Create habit (§9.5.4) -----------------------------------------------

const createSchema = z.object({
  habit: z.string().min(3).max(200),
});

export async function createStreak(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = createSchema.safeParse({
    habit: (formData.get("habit") ?? "").toString().trim(),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input." };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const cap = TIER_LIMITS[tier].drill_sergeant_scheduled;

  if (cap !== null) {
    const { count } = await supabase
      .from("streaks")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id);
    if ((count ?? 0) >= cap) {
      return {
        ok: false,
        error: `Your ${tier} tier caps scheduled habits at ${cap}.`,
      };
    }
  }

  const { error } = await supabase
    .from("streaks")
    .insert({
      user_id: user.id,
      habit: parsed.data.habit,
      current_streak: 0,
      longest_streak: 0,
    });
  if (error) return { ok: false, error: "Couldn't create habit." };

  revalidatePath("/tools/drill-sergeant");
  return { ok: true };
}

// ----- Check in -------------------------------------------------------------

const checkinSchema = z.object({ id: z.coerce.number().int().positive() });

export async function checkInStreak(formData: FormData): Promise<void> {
  const parsed = checkinSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: streak } = await supabase
    .from("streaks")
    .select("id, user_id, current_streak, longest_streak, last_checkin_at")
    .eq("id", parsed.data.id)
    .maybeSingle();
  if (!streak || streak.user_id !== user.id) return;

  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);

  if (streak.last_checkin_at === today) {
    // Already checked in.
    revalidatePath("/tools/drill-sergeant");
    return;
  }

  let nextCurrent: number;
  if (streak.last_checkin_at === yesterday) {
    nextCurrent = (streak.current_streak ?? 0) + 1;
  } else {
    nextCurrent = 1; // streak was broken or never started
  }
  const nextLongest = Math.max(streak.longest_streak ?? 0, nextCurrent);

  await supabase
    .from("streaks")
    .update({
      current_streak: nextCurrent,
      longest_streak: nextLongest,
      last_checkin_at: today,
    })
    .eq("id", parsed.data.id)
    .eq("user_id", user.id);

  revalidatePath("/tools/drill-sergeant");
}

// ----- Delete streak --------------------------------------------------------

export async function deleteStreak(formData: FormData): Promise<void> {
  const parsed = checkinSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase
    .from("streaks")
    .delete()
    .eq("id", parsed.data.id)
    .eq("user_id", user.id);

  revalidatePath("/tools/drill-sergeant");
}
