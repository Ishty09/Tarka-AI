import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { NewDisputeForm } from "./NewDisputeForm";

interface PageProps {
  params: Promise<{ linkId: string }>;
}

export default async function NewDisputePage({ params }: PageProps) {
  const { linkId } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: link } = await supabase
    .from("couple_links")
    .select("id, status, user_a, user_b")
    .eq("id", linkId)
    .maybeSingle();
  if (!link || link.status !== "active") {
    redirect("/couples");
  }
  if (user.id !== link.user_a && user.id !== link.user_b) {
    redirect("/couples");
  }

  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <Link
        href={`/couples/${linkId}`}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ← Back
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        New dispute
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Write only YOUR side. Your partner will write theirs separately —
        neither of you can read the other&apos;s perspective until both
        have submitted. When both are in, Quarrel produces a verdict you
        both see together.
      </p>
      <NewDisputeForm linkId={linkId} />
    </main>
  );
}
