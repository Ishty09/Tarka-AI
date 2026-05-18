import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { serverEnv } from "@/lib/env";
import type { ChatTurn } from "@/app/(app)/chat/_components/useChatStream";
import { archiveGroup, leaveGroup } from "../actions";
import { GroupChat } from "./GroupChat";

// /groups/[groupId] (§9.3.4). Members + invite display. The actual chat
// surface lands in step 37 once AI turn-taking + Realtime are wired.

interface PageProps {
  params: Promise<{ groupId: string }>;
}

type RoomDetail = {
  id: string;
  name: string;
  owner_id: string;
  invite_code: string | null;
  max_members: number;
  archived: boolean;
  created_at: string;
  mediator: { slug: string; name: string } | { slug: string; name: string }[] | null;
};

type MemberRow = {
  user_id: string;
  role: string;
  joined_at: string;
  profile: { username: string | null; display_name: string | null } | { username: string | null; display_name: string | null }[] | null;
};

function unwrap<T>(v: T | T[] | null): T | null {
  if (!v) return null;
  return Array.isArray(v) ? v[0] ?? null : v;
}

export default async function GroupDetailPage({ params }: PageProps) {
  const { groupId } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: roomRaw } = await supabase
    .from("group_rooms")
    .select(
      "id, name, owner_id, invite_code, max_members, archived, created_at, "
      + "mediator:personas!mediator_persona_id(slug, name)",
    )
    .eq("id", groupId)
    .maybeSingle();
  const room = roomRaw as RoomDetail | null;
  if (!room) notFound();

  const { data: membersRaw } = await supabase
    .from("group_members")
    .select("user_id, role, joined_at, profile:profiles!user_id(username, display_name)")
    .eq("group_id", groupId)
    .order("joined_at", { ascending: true });
  const members = (membersRaw ?? []) as unknown as MemberRow[];

  const youAreOwner = room.owner_id === user.id;
  const youAreMember = members.some((m) => m.user_id === user.id);
  if (!youAreMember) notFound();

  const mediator = unwrap(room.mediator);
  const seatsTaken = members.length;
  const inviteUrl = room.invite_code
    ? `/groups/join/${room.invite_code}`
    : null;

  // For active rooms, open the shared conversation via workers and hand
  // off to GroupChat. Errors fall through to the lobby view below.
  if (!room.archived && serverEnv.WORKERS_INTERNAL_SECRET) {
    const upstream = await fetch(`${serverEnv.WORKERS_URL}/tools/groups/start`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
        "x-user-id": user.id,
      },
      body: JSON.stringify({ group_id: room.id }),
      cache: "no-store",
    });
    if (upstream.ok) {
      const { conversation_id: conversationId } = (await upstream.json()) as {
        conversation_id: string;
      };
      const { data: messageRowsRaw } = await supabase
        .from("messages")
        .select("id, role, content, redacted_content, user_id, safety_verdict")
        .eq("conversation_id", conversationId)
        .in("role", ["user", "assistant"])
        .order("id", { ascending: true })
        .limit(200);
      const messageRows = (messageRowsRaw ?? []) as Array<{
        id: number;
        role: string;
        content: string;
        redacted_content: string | null;
        user_id: string | null;
        safety_verdict: string | null;
      }>;
      const memberLookup = new Map<string, string>();
      for (const m of members) {
        const p = unwrap(m.profile);
        memberLookup.set(
          m.user_id,
          p?.display_name ?? p?.username ?? "Member",
        );
      }
      const initialMessages: ChatTurn[] = messageRows.map((m) => ({
        id: String(m.id),
        role: m.role as "user" | "assistant",
        content: m.redacted_content ?? m.content,
        persistedMessageId: m.id,
        authorId: m.user_id ?? undefined,
        authorName:
          m.role === "assistant"
            ? mediator?.name ?? "Mediator"
            : m.user_id
            ? memberLookup.get(m.user_id) ?? "Member"
            : undefined,
        ...(m.safety_verdict && m.safety_verdict !== "safe"
          ? { safetyVerdict: m.safety_verdict }
          : {}),
      }));

      return (
        <GroupChat
          groupId={room.id}
          conversationId={conversationId}
          currentUserId={user.id}
          mediatorName={mediator?.name ?? "Mediator"}
          members={Array.from(memberLookup.entries()).map(([id, name]) => ({ id, name }))}
          initialMessages={initialMessages}
        />
      );
    }
  }

  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <Link href="/groups" className="text-sm text-muted-foreground hover:underline">
        ← Groups
      </Link>
      <header className="mt-2 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{room.name}</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Mediator: <span className="font-medium text-foreground">{mediator?.name ?? "—"}</span>
            {" · "}
            {seatsTaken} / {room.max_members} seats
            {room.archived ? " · archived" : ""}
          </p>
        </div>
        {!room.archived && (
          <div className="flex items-center gap-2">
            <form action={leaveGroup}>
              <input type="hidden" name="group_id" value={room.id} />
              <button
                type="submit"
                className="rounded-md border border-input bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                {youAreOwner ? "Archive" : "Leave"}
              </button>
            </form>
            {youAreOwner && (
              <form action={archiveGroup}>
                <input type="hidden" name="group_id" value={room.id} />
                <button
                  type="submit"
                  className="rounded-md border border-input bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  Archive room
                </button>
              </form>
            )}
          </div>
        )}
      </header>

      {!room.archived && youAreOwner && inviteUrl && (
        <section className="mt-6 rounded-md border border-input bg-muted/30 p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Invite link
          </h2>
          <p className="mt-2 break-all font-mono text-xs">{inviteUrl}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Share with up to {room.max_members - 1} other people.
          </p>
        </section>
      )}

      <section className="mt-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Members
        </h2>
        <ul className="mt-3 flex flex-col gap-2">
          {members.map((m) => {
            const p = unwrap(m.profile);
            return (
              <li
                key={m.user_id}
                className="flex items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <span>
                  {p?.display_name ?? p?.username ?? "—"}
                  {m.user_id === user.id && (
                    <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                  )}
                </span>
                <span className="text-xs text-muted-foreground capitalize">{m.role}</span>
              </li>
            );
          })}
        </ul>
      </section>

      {!room.archived && (
        <section className="mt-8 rounded-md border border-input bg-muted/30 p-4 text-sm">
          <p className="text-muted-foreground">
            Group chat with AI turn-taking ships in the next step. For now this
            is the lobby — invite, leave, or archive.
          </p>
        </section>
      )}
    </main>
  );
}
