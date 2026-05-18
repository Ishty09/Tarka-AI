import { redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { JoinGroupForm } from "./JoinGroupForm";

interface PageProps {
  params: Promise<{ code: string }>;
}

type RoomLookup = {
  id: string;
  name: string;
  owner_id: string;
  archived: boolean;
  max_members: number;
};

export default async function JoinGroupPage({ params }: PageProps) {
  const { code } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    redirect(`/login?next=/groups/join/${encodeURIComponent(code)}`);
  }

  const { data: roomRaw } = await supabase
    .from("group_rooms")
    .select("id, name, owner_id, archived, max_members")
    .eq("invite_code", code)
    .maybeSingle();
  const room = roomRaw as RoomLookup | null;

  if (!room) {
    return (
      <main className="mx-auto w-full max-w-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Group not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The link may have been mistyped or the room was archived.
        </p>
        <Link href="/groups" className="mt-4 inline-block text-sm underline">
          Go to groups
        </Link>
      </main>
    );
  }

  if (room.archived) {
    return (
      <main className="mx-auto w-full max-w-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">This group was archived</h1>
        <Link href="/groups" className="mt-4 inline-block text-sm underline">
          Back to groups
        </Link>
      </main>
    );
  }

  // Already a member? Skip the prompt.
  const { data: existingMember } = await supabase
    .from("group_members")
    .select("user_id")
    .eq("group_id", room.id)
    .eq("user_id", user.id)
    .maybeSingle();
  if (existingMember) {
    redirect(`/groups/${room.id}`);
  }

  const { count } = await supabase
    .from("group_members")
    .select("user_id", { count: "exact", head: true })
    .eq("group_id", room.id);

  const seatsTaken = count ?? 0;
  const full = seatsTaken >= room.max_members;

  return (
    <main className="mx-auto w-full max-w-xl p-6">
      <h1 className="text-2xl font-semibold tracking-tight">Join “{room.name}”</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {full
          ? `This room is full (${seatsTaken}/${room.max_members}). Ask the owner to remove someone or bump the cap.`
          : `${seatsTaken} of ${room.max_members} seats taken.`}
      </p>
      {!full && (
        <div className="mt-6">
          <JoinGroupForm inviteCode={code} />
        </div>
      )}
    </main>
  );
}
