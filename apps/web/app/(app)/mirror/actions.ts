"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

// Stamps mirror_reports.viewed_at when the user opens a report. Run via a
// hidden form on the page so we don't need client-side fetch + state. RLS
// (§6.7 mirror_self) scopes the write to the signed-in user.

const idSchema = z.object({ id: z.string().uuid() });

export async function markMirrorViewed(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase
    .from("mirror_reports")
    .update({ viewed_at: new Date().toISOString() })
    .eq("id", parsed.data.id)
    .is("viewed_at", null);

  revalidatePath("/mirror");
}
