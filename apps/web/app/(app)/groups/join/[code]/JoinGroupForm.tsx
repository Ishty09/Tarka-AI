"use client";

import Link from "next/link";
import { useActionState } from "react";
import { joinGroup, type ActionResult } from "../../actions";

export function JoinGroupForm({ inviteCode }: { inviteCode: string }) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(
    joinGroup,
    null,
  );
  return (
    <form action={action} className="flex flex-col gap-3">
      <input type="hidden" name="invite_code" value={inviteCode} />
      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">
          {state.error}
          {state.upgrade && (
            <>
              {" "}
              <Link href="/pricing" className="font-medium underline">
                Upgrade →
              </Link>
            </>
          )}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Joining…" : "Join room"}
      </button>
    </form>
  );
}
