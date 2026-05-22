"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { hashUserId, trackServer } from "@/lib/analytics";
import { createServerSupabase } from "@/lib/supabase/server";

// Stamps eulogy_reports.viewed_at when the user opens a report. RLS
// (§6.7 eulogy_self) scopes the write to the signed-in user.

const idSchema = z.object({ id: z.string().uuid() });

export async function markEulogyViewed(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: updated } = await supabase
    .from("eulogy_reports")
    .update({ viewed_at: new Date().toISOString() })
    .eq("id", parsed.data.id)
    .is("viewed_at", null)
    .select("id");

  if (updated && updated.length > 0) {
    await trackServer("eulogy_viewed", {
      user_id: hashUserId(user.id),
      report_id: parsed.data.id,
    });
  }
  revalidatePath("/eulogy");
}
