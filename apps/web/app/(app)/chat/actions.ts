"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createServerSupabase } from "@/lib/supabase/server";

// All conversation mutations run through the user's authenticated Supabase
// client — RLS (§6.7 conversations_owner) is the only gate. Service-role
// stays in workers (§1.3).

const idSchema = z.object({ id: z.string().uuid() });

const renameSchema = z.object({
  id: z.string().uuid(),
  title: z.string().min(1).max(120),
});

export async function archiveConversation(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase
    .from("conversations")
    .update({ archived: true })
    .eq("id", parsed.data.id);

  revalidatePath("/chat");
}

export async function unarchiveConversation(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase
    .from("conversations")
    .update({ archived: false })
    .eq("id", parsed.data.id);

  revalidatePath("/chat");
}

export async function renameConversation(formData: FormData): Promise<void> {
  const parsed = renameSchema.safeParse({
    id: formData.get("id"),
    title: (formData.get("title") ?? "").toString().trim(),
  });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase
    .from("conversations")
    .update({ title: parsed.data.title })
    .eq("id", parsed.data.id);

  revalidatePath(`/chat/${parsed.data.id}`);
  revalidatePath("/chat");
}

export async function archiveAndReturnHome(formData: FormData): Promise<void> {
  await archiveConversation(formData);
  redirect("/chat");
}
