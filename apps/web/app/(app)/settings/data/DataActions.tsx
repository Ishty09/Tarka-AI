"use client";

import { useState, useTransition } from "react";
import {
  cancelAccountDeletion,
  requestAccountDeletion,
  requestDataExport,
} from "../actions";

interface Props {
  deletionRequestedAt: string | null;
  username: string;
}

export function DataActions({ deletionRequestedAt, username }: Props) {
  const [pending, start] = useTransition();
  const [confirm, setConfirm] = useState("");
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  const armed = confirm.trim().toLowerCase() === username.trim().toLowerCase();

  const graceEnds = deletionRequestedAt
    ? new Date(new Date(deletionRequestedAt).getTime() + 30 * 86_400_000)
    : null;

  function onExport() {
    setExportMsg(null);
    start(async () => {
      const r = await requestDataExport();
      setExportMsg(r.ok ? "Export queued. Watch your inbox." : r.error);
    });
  }

  function onRequestDelete() {
    if (!armed) return;
    start(async () => {
      await requestAccountDeletion();
    });
  }

  function onCancelDelete() {
    start(async () => {
      await cancelAccountDeletion();
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">Export your data</h3>
        <p className="text-xs text-muted-foreground">
          We&apos;ll email you a signed link to a JSON of everything we hold
          about you. Available within 30 days under GDPR.
        </p>
        <button
          type="button"
          disabled={pending}
          onClick={onExport}
          className="inline-flex w-fit items-center justify-center rounded-md border border-input px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent disabled:opacity-50"
        >
          {pending ? "Queueing..." : "Request export"}
        </button>
        {exportMsg && <p className="text-xs text-muted-foreground">{exportMsg}</p>}
      </section>

      <hr className="border-input" />

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-destructive">Delete your account</h3>
        {deletionRequestedAt ? (
          <>
            <p className="text-xs text-muted-foreground">
              Deletion is queued. Final removal on{" "}
              <strong>{graceEnds?.toLocaleDateString()}</strong>. You can sign
              in any time before then to cancel.
            </p>
            <button
              type="button"
              disabled={pending}
              onClick={onCancelDelete}
              className="inline-flex w-fit items-center justify-center rounded-md border border-input px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent disabled:opacity-50"
            >
              {pending ? "Cancelling..." : "Cancel deletion"}
            </button>
          </>
        ) : (
          <>
            <p className="text-xs text-muted-foreground">
              30-day grace period. Type your username (<code>{username}</code>)
              to confirm.
            </p>
            <input
              type="text"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder={username}
              className="w-64 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <button
              type="button"
              disabled={!armed || pending}
              onClick={onRequestDelete}
              className="inline-flex w-fit items-center justify-center rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
            >
              {pending ? "Queueing..." : "Delete my account"}
            </button>
          </>
        )}
      </section>
    </div>
  );
}
