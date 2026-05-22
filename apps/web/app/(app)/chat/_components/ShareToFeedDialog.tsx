"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { track } from "@/lib/analytics/client";

interface Props {
  messageId: number;
  open: boolean;
  onClose: () => void;
}

interface SuccessState {
  postId: string;
  status: "approved" | "flagged";
}

export function ShareToFeedDialog({ messageId, open, onClose }: Props) {
  const [caption, setCaption] = useState("");
  const [visibility, setVisibility] = useState<"public" | "unlisted">("public");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<SuccessState | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  useEffect(() => {
    if (!open) {
      setCaption("");
      setVisibility("public");
      setPending(false);
      setError(null);
      setSuccess(null);
    }
  }, [open]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/feed/submit", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          message_id: messageId,
          caption: caption.trim() || undefined,
          visibility,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.status === 429) {
        setError(
          `Daily limit (${body.used}/${body.limit}). ${body.tier === "free" ? "Upgrade to share to the feed." : "Try again tomorrow."}`,
        );
        return;
      }
      if (res.status === 422) {
        setError(
          `Moderation: ${body.reason ?? "rejected"}${
            Array.isArray(body.categories) && body.categories.length
              ? ` (${body.categories.join(", ")})`
              : ""
          }`,
        );
        return;
      }
      if (!res.ok) {
        setError(body.error ?? body.reason ?? `Failed (${res.status})`);
        return;
      }
      setSuccess({
        postId: body.post?.id ?? "",
        status: body.post?.moderation_status === "flagged" ? "flagged" : "approved",
      });
      track("roast_feed_post_created", {
        post_id: body.post?.id,
        moderation_status: body.post?.moderation_status,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setPending(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      className="rounded-lg border border-input bg-background p-0 shadow-xl backdrop:bg-black/40"
    >
      <div className="w-[min(28rem,calc(100vw-2rem))] p-5">
        <header className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Share to feed</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Auto-moderated. Approved posts appear in /feed within seconds.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        {success ? (
          <div className="mt-4 flex flex-col gap-3">
            <p
              className={`rounded-md border p-3 text-sm ${
                success.status === "approved"
                  ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-800 dark:text-emerald-200"
                  : "border-amber-500/40 bg-amber-500/10 text-amber-800 dark:text-amber-200"
              }`}
            >
              {success.status === "approved"
                ? "Posted. It's live in /feed."
                : "Flagged for review. It's saved as unlisted while a human checks it."}
            </p>
            <div className="flex justify-end gap-2">
              <Link
                href="/feed"
                className="rounded-md border border-input bg-background px-3 py-1.5 text-xs hover:bg-accent"
              >
                Go to feed
              </Link>
              <button
                type="button"
                onClick={onClose}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3">
            <label htmlFor="caption" className="text-sm font-medium">Caption (optional)</label>
            <input
              id="caption"
              maxLength={280}
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Give context for the feed."
              className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-medium">Visibility</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="flex items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5">
                  <input
                    type="radio"
                    name="visibility"
                    value="public"
                    checked={visibility === "public"}
                    onChange={() => setVisibility("public")}
                  />
                  <span>Public · in /feed</span>
                </label>
                <label className="flex items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5">
                  <input
                    type="radio"
                    name="visibility"
                    value="unlisted"
                    checked={visibility === "unlisted"}
                    onChange={() => setVisibility("unlisted")}
                  />
                  <span>Unlisted · link only</span>
                </label>
              </div>
            </fieldset>

            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-xs hover:bg-accent"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={pending}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
              >
                {pending ? "Sharing…" : "Share"}
              </button>
            </div>
          </form>
        )}
      </div>
    </dialog>
  );
}
