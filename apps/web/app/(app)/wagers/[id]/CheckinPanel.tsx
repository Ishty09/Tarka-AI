"use client";

import { useActionState, useMemo, useState } from "react";
import { createCheckin, type ActionResult } from "../actions";

interface Checkin {
  checkin_date: string;
  status: "completed" | "missed" | "skipped";
  notes: string | null;
  proof_url: string | null;
}

interface Props {
  wagerId: string;
  startAt: string;
  endAt: string;
  todayIso: string;
  checkins: Checkin[];
}

const STATUS_LABEL: Record<Checkin["status"], string> = {
  completed: "Completed",
  missed: "Missed",
  skipped: "Skipped",
};

const STATUS_TONE: Record<Checkin["status"], string> = {
  completed: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700",
  missed: "border-red-500/40 bg-red-500/10 text-red-700",
  skipped: "border-input bg-muted/30 text-muted-foreground",
};

function daysBetween(startIso: string, endIso: string): string[] {
  const out: string[] = [];
  const start = new Date(startIso);
  const end = new Date(endIso);
  const cursor = new Date(start);
  while (cursor.getTime() <= end.getTime()) {
    out.push(cursor.toISOString().slice(0, 10));
    cursor.setDate(cursor.getDate() + 1);
  }
  return out;
}

export function CheckinPanel({
  wagerId,
  startAt,
  endAt,
  todayIso,
  checkins,
}: Props) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(
    createCheckin,
    null,
  );

  const byDate = useMemo(() => {
    const map = new Map<string, Checkin>();
    for (const c of checkins) map.set(c.checkin_date, c);
    return map;
  }, [checkins]);

  const days = useMemo(() => {
    const all = daysBetween(startAt, endAt);
    // Show at most the trailing 30 days so long wagers don't overflow.
    return all.slice(-30);
  }, [startAt, endAt]);

  const todayInWindow = todayIso >= startAt && todayIso <= endAt;
  const todayCheckin = byDate.get(todayIso);

  const [pickedStatus, setPickedStatus] = useState<Checkin["status"] | "">(
    todayCheckin?.status ?? "",
  );

  return (
    <section className="mt-6 flex flex-col gap-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Check-ins
      </h2>

      <div className="grid grid-cols-7 gap-1 sm:grid-cols-10">
        {days.map((d) => {
          const c = byDate.get(d);
          const isToday = d === todayIso;
          const isFuture = d > todayIso;
          const tone = c
            ? STATUS_TONE[c.status]
            : isToday
            ? "border-primary/40 bg-primary/5"
            : isFuture
            ? "border-dashed border-input/60 bg-background text-muted-foreground"
            : "border-input bg-muted/20 text-muted-foreground";
          return (
            <div
              key={d}
              title={`${d}${c ? ` · ${STATUS_LABEL[c.status]}` : isFuture ? " · upcoming" : " · no check-in"}`}
              className={`flex aspect-square flex-col items-center justify-center rounded border text-[10px] ${tone}`}
            >
              <span className="font-mono">{d.slice(5)}</span>
              {c && <span className="mt-0.5">{c.status[0].toUpperCase()}</span>}
            </div>
          );
        })}
      </div>

      {todayInWindow ? (
        <form action={action} className="flex flex-col gap-3 rounded-md border border-input bg-background p-4 shadow-sm">
          <input type="hidden" name="wager_id" value={wagerId} />
          <input type="hidden" name="checkin_date" value={todayIso} />
          <input type="hidden" name="status" value={pickedStatus} />

          <p className="text-sm font-medium">
            How&apos;d today go?{" "}
            <span className="text-xs text-muted-foreground">({todayIso})</span>
          </p>
          {todayCheckin && (
            <p className="text-xs text-muted-foreground">
              You marked today {STATUS_LABEL[todayCheckin.status].toLowerCase()}. You can change it.
            </p>
          )}

          <div className="grid gap-2 sm:grid-cols-3">
            {(["completed", "missed", "skipped"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setPickedStatus(s)}
                aria-pressed={pickedStatus === s}
                className={`rounded-md border px-3 py-2 text-sm shadow-sm transition ${
                  pickedStatus === s
                    ? STATUS_TONE[s] + " border-2"
                    : "border-input bg-background hover:bg-accent"
                }`}
              >
                {STATUS_LABEL[s]}
              </button>
            ))}
          </div>

          <label className="flex flex-col gap-1 text-xs font-medium">
            Notes (optional)
            <textarea
              name="notes"
              maxLength={1000}
              rows={2}
              placeholder="What happened?"
              defaultValue={todayCheckin?.notes ?? ""}
              className="resize-none rounded-md border border-input bg-background px-3 py-2 text-xs shadow-sm"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium">
            Proof URL (optional)
            <input
              name="proof_url"
              type="url"
              placeholder="https://… screenshot, Strava link, anything"
              defaultValue={todayCheckin?.proof_url ?? ""}
              className="rounded-md border border-input bg-background px-3 py-2 text-xs shadow-sm"
            />
          </label>

          {state?.ok === false && (
            <p role="alert" className="text-xs text-destructive">{state.error}</p>
          )}
          {state?.ok && (
            <p className="text-xs text-emerald-700">Saved.</p>
          )}

          <button
            type="submit"
            disabled={pending || !pickedStatus}
            className="self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "Saving…" : "Save check-in"}
          </button>
        </form>
      ) : (
        <p className="text-xs text-muted-foreground">
          Today ({todayIso}) is outside the wager window — start was {startAt}, end was {endAt}.
        </p>
      )}
    </section>
  );
}
