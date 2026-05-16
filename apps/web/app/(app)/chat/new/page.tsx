import { redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { ChatThread } from "../_components/ChatThread";

// /chat/new?persona=<slug> opens a blank thread with that persona selected.
// The first user message creates the conversation row in workers and the
// onAssistantPersisted callback refreshes so the conversation appears in
// the list. Without ?persona we punt to /personas — the worker requires
// either an existing conversation_id or a persona_slug.

interface PageProps {
  searchParams: Promise<{ persona?: string; mode?: string }>;
}

export default async function NewChatPage({ searchParams }: PageProps) {
  const { persona: personaSlug, mode: modeParam } = await searchParams;

  if (!personaSlug) {
    return (
      <main className="mx-auto w-full max-w-2xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Pick a persona</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          You need a persona to start a chat. Pick one from the library.
        </p>
        <Link
          href="/personas"
          className="mt-4 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          Browse personas
        </Link>
      </main>
    );
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: persona } = await supabase
    .from("personas")
    .select("slug, name, category")
    .eq("slug", personaSlug)
    .maybeSingle();

  if (!persona) {
    return (
      <main className="mx-auto w-full max-w-2xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Persona not found</h1>
        <Link href="/personas" className="mt-4 inline-block text-sm underline">
          Browse personas
        </Link>
      </main>
    );
  }

  // Map persona category → conversation mode. Anything outside the chat
  // modes (productivity tools, council) gets its own routes later.
  const mode = pickModeForCategory(persona.category, modeParam);

  return (
    <ChatThread
      conversationId={null}
      personaSlug={persona.slug}
      personaName={persona.name}
      mode={mode}
      initialMessages={[]}
    />
  );
}

function pickModeForCategory(
  category: string,
  override?: string,
): "argue" | "roast" | "mediate" | "council" | "negotiate" | "custom" {
  if (override === "argue" || override === "roast" || override === "mediate") return override;
  switch (category) {
    case "argue":
      return "argue";
    case "roast":
      return "roast";
    case "mediate":
      return "mediate";
    case "council":
      return "council";
    default:
      return "custom";
  }
}
