"use client";

import { useTransition } from "react";
import { setCoupleCrossFactConsent } from "../actions";

interface Props {
  coupleLinkId: string;
  partnerName: string;
  enabled: boolean;
  partnerConsent: boolean;
}

export function CrossFactToggle({
  coupleLinkId,
  partnerName,
  enabled,
  partnerConsent,
}: Props) {
  const [pending, start] = useTransition();
  // Cross-fact retrieval is gated by §6.7 get_couple_facts(): BOTH partners
  // must say yes. If the partner hasn't consented yet, toggling on still
  // succeeds — the actual fact retrieval will still refuse server-side until
  // both flags are true. The UI just notes this.

  function onToggle(next: boolean) {
    const fd = new FormData();
    fd.set("couple_link_id", coupleLinkId);
    if (next) fd.set("enabled", "on");
    start(async () => {
      await setCoupleCrossFactConsent(fd);
    });
  }

  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-input p-3">
      <div>
        <p className="text-sm font-medium">{partnerName}</p>
        {!partnerConsent && (
          <p className="text-[11px] text-amber-600">
            Your partner hasn&apos;t toggled this yet — retrieval stays off until both
            of you do.
          </p>
        )}
      </div>
      <label className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">
          {enabled ? "Consented" : "Off"}
        </span>
        <input
          type="checkbox"
          checked={enabled}
          disabled={pending}
          onChange={(e) => onToggle(e.currentTarget.checked)}
          className="size-4 rounded border-input"
        />
      </label>
    </div>
  );
}
