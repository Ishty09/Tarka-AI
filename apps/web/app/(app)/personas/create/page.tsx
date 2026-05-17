import { redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { CreatePersonaForm } from "./CreatePersonaForm";

export default async function CreatePersonaPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("locale")
    .eq("id", user.id)
    .maybeSingle();

  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <Link href="/personas" className="text-sm text-muted-foreground hover:underline">
        ← Personas
      </Link>
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">Create a persona</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Private until moderation passes. You can use it yourself immediately.
      </p>

      <div className="mt-6">
        <CreatePersonaForm defaultLocale={profile?.locale ?? "en"} />
      </div>
    </main>
  );
}
