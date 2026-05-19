"use client";

import Link from "next/link";
import { useFormState, useFormStatus } from "react-dom";
import {
  approveFeedPostAction,
  rejectFeedPostAction,
  removeFeedPostAction,
  type ActionResult,
} from "../actions";

interface Props {
  post: {
    id: string;
    user_id: string;
    conversation_id: string;
    message_id: number;
    caption: string | null;
    moderation_status: string;
    visibility: string;
    created_at: string;
  };
}

const initialState: ActionResult | null = null;

export function FeedPostRow({ post }: Props) {
  const [approveState, approveAction] = useFormState(approveFeedPostAction, initialState);
  const [rejectState, rejectAction] = useFormState(rejectFeedPostAction, initialState);
  const [removeState, removeAction] = useFormState(removeFeedPostAction, initialState);
  const lastError =
    (approveState && !approveState.ok && approveState.error) ||
    (rejectState && !rejectState.ok && rejectState.error) ||
    (removeState && !removeState.ok && removeState.error) ||
    null;

  return (
    <article className="flex flex-col gap-3 rounded-md border border-input bg-card p-4 shadow-sm">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold">
            {post.caption ? `"${post.caption}"` : <em>no caption</em>}
          </h3>
          <p className="text-[11px] text-muted-foreground">
            <Link href={`/chat/${post.conversation_id}`} className="underline">
              View source chat →
            </Link>{" "}
            · {post.moderation_status} · {new Date(post.created_at).toLocaleString()}
          </p>
        </div>
      </header>
      <div className="flex flex-wrap items-center gap-2">
        <form action={approveAction} className="contents">
          <input type="hidden" name="post_id" value={post.id} />
          <SubmitButton label="Approve" variant="primary" />
        </form>
        <form action={rejectAction} className="contents">
          <input type="hidden" name="post_id" value={post.id} />
          <SubmitButton label="Reject" variant="destructive" />
        </form>
        {post.moderation_status === "approved" && (
          <form action={removeAction} className="contents">
            <input type="hidden" name="post_id" value={post.id} />
            <SubmitButton label="Remove" variant="destructive" />
          </form>
        )}
      </div>
      {lastError && (
        <p role="alert" className="text-xs text-destructive">{lastError}</p>
      )}
    </article>
  );
}

function SubmitButton({
  label,
  variant,
}: {
  label: string;
  variant: "primary" | "destructive";
}) {
  const { pending } = useFormStatus();
  const cls =
    variant === "primary"
      ? "bg-primary text-primary-foreground"
      : "bg-destructive text-destructive-foreground";
  return (
    <button
      type="submit"
      disabled={pending}
      className={`inline-flex items-center justify-center rounded-md ${cls} px-3 py-1 text-xs font-medium shadow-sm hover:opacity-90 disabled:opacity-50`}
    >
      {pending ? "..." : label}
    </button>
  );
}
