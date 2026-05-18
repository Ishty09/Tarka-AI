"use client";

import { useActionState } from "react";
import { acceptInvite, type ActionResult } from "../../actions";

export function JoinForm({ inviteCode }: { inviteCode: string }) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(
    acceptInvite,
    null,
  );

  return (
    <form action={action} className="flex flex-col gap-3">
      <input type="hidden" name="invite_code" value={inviteCode} />
      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">{state.error}</p>
      )}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Accepting…" : "Accept and open chat"}
        </button>
      </div>
    </form>
  );
}
