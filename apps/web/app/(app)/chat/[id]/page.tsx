import { notFound, redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { ChatThread } from "../_components/ChatThread";
import type { ChatTurn } from "../_components/useChatStream";

type AllowedMode = "argue" | "roast" | "mediate" | "council" | "negotiate" | "custom";
const ALLOWED_MODES = new Set<AllowedMode>([
  "argue",
  "roast",
  "mediate",
  "council",
  "negotiate",
  "custom",
]);

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function ChatPage({ params }: PageProps) {
  const { id } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: conversation } = await supabase
    .from("conversations")
    .select("id, mode, persona:personas(slug, name)")
    .eq("id", id)
    .maybeSingle();

  if (!conversation) notFound();

  const persona = Array.isArray(conversation.persona)
    ? conversation.persona[0]
    : conversation.persona;

  const { data: messages } = await supabase
    .from("messages")
    .select("id, role, content, redacted_content, safety_verdict")
    .eq("conversation_id", id)
    .in("role", ["user", "assistant"])
    .order("id", { ascending: true })
    .limit(50);

  const initialMessages: ChatTurn[] = (messages ?? []).map((m) => ({
    id: String(m.id),
    role: m.role as "user" | "assistant",
    content: m.redacted_content ?? m.content,
    ...(m.safety_verdict && m.safety_verdict !== "safe"
      ? { safetyVerdict: m.safety_verdict }
      : {}),
  }));

  const mode: AllowedMode = ALLOWED_MODES.has(conversation.mode as AllowedMode)
    ? (conversation.mode as AllowedMode)
    : "custom";

  return (
    <ChatThread
      conversationId={conversation.id}
      personaSlug={null}
      personaName={persona?.name ?? "Persona"}
      mode={mode}
      initialMessages={initialMessages}
    />
  );
}
