"use client";

import { useFormState, useFormStatus } from "react-dom";
import {
  suspendUserAction,
  unsuspendUserAction,
  type ActionResult,
} from "../actions";

interface Props {
  user: {
    id: string;
    username: string;
    display_name: string | null;
    tier: string;
    is_admin: boolean;
    is_suspended: boolean;
    suspension_reason: string | null;
    created_at: string;
  };
}

const initialState: ActionResult | null = null;

export function UserRow({ user }: Props) {
  const [state, action] = useFormState(suspendUserAction, initialState);
  return (
    <article className="flex flex-col gap-2 rounded-md border border-input bg-card p-4 shadow-sm">
      <header className="flex items-baseline justify-between">
        <div>
          <h3 className="text-sm font-semibold">
            @{user.username}
            {user.is_admin && (
              <span className="ml-2 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] uppercase text-amber-700">
                Admin
              </span>
            )}
            {user.is_suspended && (
              <span className="ml-2 rounded bg-destructive/20 px-1.5 py-0.5 text-[10px] uppercase text-destructive">
                Suspended
              </span>
            )}
          </h3>
          <p className="text-[11px] text-muted-foreground">
            {user.display_name ?? "—"} · {user.tier} ·{" "}
            {new Date(user.created_at).toLocaleDateString()}
          </p>
          {user.is_suspended && user.suspension_reason && (
            <p className="mt-1 text-xs italic text-muted-foreground">
              Reason: {user.suspension_reason}
            </p>
          )}
        </div>
      </header>

      {user.is_suspended ? (
        <form action={unsuspendUserAction} className="flex items-center gap-2">
          <input type="hidden" name="user_id" value={user.id} />
          <UnsuspendButton />
        </form>
      ) : (
        <form action={action} className="flex flex-wrap items-center gap-2">
          <input type="hidden" name="user_id" value={user.id} />
          <input
            type="text"
            name="reason"
            placeholder="Why are you suspending?"
            minLength={3}
            maxLength={1000}
            required
            className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-xs"
          />
          <SuspendButton />
        </form>
      )}
      {state && !state.ok && (
        <p role="alert" className="text-xs text-destructive">{state.error}</p>
      )}
    </article>
  );
}

function SuspendButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="inline-flex items-center justify-center rounded-md bg-destructive px-3 py-1 text-xs font-medium text-destructive-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
    >
      {pending ? "..." : "Suspend"}
    </button>
  );
}

function UnsuspendButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1 text-xs font-medium shadow-sm hover:bg-accent disabled:opacity-50"
    >
      {pending ? "..." : "Unsuspend"}
    </button>
  );
}
