import { redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { JoinForm } from "./JoinForm";

interface PageProps {
  params: Promise<{ code: string }>;
}

type InviteLookup = {
  id: string;
  user_a: string;
  user_b: string | null;
  status: string;
  invite_expires_at: string | null;
  creator: { username: string | null; display_name: string | null } | { username: string | null; display_name: string | null }[] | null;
};

function unwrap<T>(v: T | T[] | null): T | null {
  if (!v) return null;
  return Array.isArray(v) ? v[0] ?? null : v;
}

export default async function JoinInvitePage({ params }: PageProps) {
  const { code } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect(`/login?next=/couples/join/${encodeURIComponent(code)}`);

  const { data: linkRaw } = await supabase
    .from("couple_links")
    .select(
      "id, user_a, user_b, status, invite_expires_at, creator:profiles!user_a(username, display_name)",
    )
    .eq("invite_code", code)
    .maybeSingle();
  const link = linkRaw as InviteLookup | null;

  if (!link) {
    return (
      <main className="mx-auto w-full max-w-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Invite not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The link might have been used, revoked, or mistyped.
        </p>
        <Link href="/couples" className="mt-4 inline-block text-sm underline">
          Go to couples
        </Link>
      </main>
    );
  }

  if (link.user_a === user.id) {
    return (
      <main className="mx-auto w-full max-w-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">That&apos;s your own invite</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Share the URL with your partner instead of opening it yourself.
        </p>
        <Link href="/couples" className="mt-4 inline-block text-sm underline">
          Back to couples
        </Link>
      </main>
    );
  }

  if (link.status !== "pending" || link.user_b !== null) {
    return (
      <main className="mx-auto w-full max-w-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Invite no longer available</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {link.status === "active"
            ? "It's already been accepted by someone else."
            : `Status: ${link.status}.`}
        </p>
        <Link href="/couples" className="mt-4 inline-block text-sm underline">
          Back to couples
        </Link>
      </main>
    );
  }

  const expired = link.invite_expires_at && new Date(link.invite_expires_at) < new Date();
  if (expired) {
    return (
      <main className="mx-auto w-full max-w-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">This invite expired</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Ask your partner to send a fresh one.
        </p>
        <Link href="/couples" className="mt-4 inline-block text-sm underline">
          Back to couples
        </Link>
      </main>
    );
  }

  const creator = unwrap(link.creator);

  return (
    <main className="mx-auto w-full max-w-xl p-6">
      <h1 className="text-2xl font-semibold tracking-tight">
        Accept invite from {creator?.display_name ?? creator?.username ?? "your partner"}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        You&apos;re about to open a shared chat with this person. The AI mediates
        — it sees both sides of the conversation. Either of you can end the
        link at any time.
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        Expires {link.invite_expires_at ? new Date(link.invite_expires_at).toLocaleDateString() : "—"}.
      </p>
      <div className="mt-6">
        <JoinForm inviteCode={code} />
      </div>
    </main>
  );
}
