"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

// Contradiction Wall actions. Both run as the authenticated user — RLS
// (§6.7 contradictions_self) is the only gate. Service-role stays in
// workers (§1.3).

const idSchema = z.object({ id: z.coerce.number().int().positive() });

export async function dismissContradiction(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase
    .from("contradictions")
    .update({ dismissed_at: new Date().toISOString() })
    .eq("id", parsed.data.id);

  revalidatePath("/contradictions");
}

export async function acknowledgeContradiction(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase
    .from("contradictions")
    .update({ acknowledged_at: new Date().toISOString() })
    .eq("id", parsed.data.id);

  revalidatePath("/contradictions");
}
