"use client";

import { useActionState, useState } from "react";
import Link from "next/link";
import { createGroup, type ActionResult } from "../actions";

interface Persona {
  slug: string;
  name: string;
  category: string;
}

interface InvitePayload {
  group_id: string;
  invite_code: string;
}

function inviteUrl(code: string): string {
  if (typeof window === "undefined") return `/groups/join/${code}`;
  return `${window.location.origin}/groups/join/${code}`;
}

export function CreateGroupForm({
  seatCap,
  personas,
}: {
  seatCap: number;
  personas: Persona[];
}) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(
    createGroup,
    null,
  );
  const defaultSlug =
    personas.find((p) => p.slug === "the_therapist")?.slug
    ?? personas[0]?.slug
    ?? "";
  const [seats, setSeats] = useState(Math.min(5, seatCap));
  const [copied, setCopied] = useState(false);

  if (state?.ok && state.payload) {
    const payload = state.payload as InvitePayload;
    const url = inviteUrl(payload.invite_code);
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm font-medium">Room is live. Share the invite.</p>
        <div className="flex items-center gap-2">
          <input
            readOnly
            value={url}
            className="flex-1 rounded-md border border-input bg-muted/30 px-3 py-2 font-mono text-xs"
          />
          <button
            type="button"
            onClick={async () => {
              await navigator.clipboard.writeText(url);
              setCopied(true);
            }}
            className="rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground hover:opacity-90"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          One invite link, valid until you archive the room. Re-rolling
          codes ships later.
        </p>
        <div className="flex gap-2">
          <Link
            href="/groups"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm hover:bg-accent"
          >
            All groups
          </Link>
          <Link
            href={`/groups/${payload.group_id}`}
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Open room
          </Link>
        </div>
      </div>
    );
  }

  return (
    <form action={action} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm font-medium">
        Room name
        <input
          name="name"
          required
          minLength={2}
          maxLength={80}
          placeholder="e.g. Founder pivot decision"
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
        />
      </label>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Seats (including you) · max {seatCap}
        <input
          name="max_members"
          type="number"
          min={2}
          max={seatCap}
          value={seats}
          onChange={(e) => setSeats(Number(e.target.value))}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
        />
      </label>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Mediator persona
        <select
          name="mediator_persona_slug"
          defaultValue={defaultSlug}
          required
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
        >
          {personas.map((p) => (
            <option key={p.slug} value={p.slug}>
              {p.name} · {p.category}
            </option>
          ))}
        </select>
        <span className="text-xs text-muted-foreground">
          The AI plays this voice in the group. You can replace it once the
          per-room persona switcher ships.
        </span>
      </label>

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
        disabled={pending || personas.length === 0}
        className="self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Creating…" : "Create room"}
      </button>
    </form>
  );
}
