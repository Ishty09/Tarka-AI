"use client";

import { useActionState, useState } from "react";
import Link from "next/link";
import type { Tier } from "@quarrel/shared/constants";
import { createWager, type ActionResult } from "../actions";

interface AntiCharity {
  slug: string;
  name: string;
  description: string;
  ideological_tag: string;
}

interface Props {
  tier: Tier;
  minStake: number;
  maxStake: number;
  antiCharities: AntiCharity[];
  polarEnabled: boolean;
}

interface CreatePayload {
  wager_id: string;
  status: string;
  polar_enabled: boolean;
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function nDaysFromTodayISO(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export function CreateWagerForm({
  tier,
  minStake,
  maxStake,
  antiCharities,
  polarEnabled,
}: Props) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(
    createWager,
    null,
  );
  const [stakeDollars, setStakeDollars] = useState((maxStake / 200).toFixed(0)); // ~half max
  const [acknowledgedCharity, setAcknowledgedCharity] = useState("");

  if (state?.ok && state.payload) {
    const payload = state.payload as CreatePayload;
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm font-medium">Wager created.</p>
        <p className="text-sm text-muted-foreground">
          Status:{" "}
          <span className="font-medium text-foreground">{payload.status}</span>.{" "}
          {payload.polar_enabled
            ? "We've initiated the hold via Polar — check your email to confirm payment."
            : "Polar is disabled during pre-launch; the wager went straight to active for the dry run."}
        </p>
        <div className="flex gap-2">
          <Link
            href="/wagers"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm hover:bg-accent"
          >
            All wagers
          </Link>
          <Link
            href={`/wagers/${payload.wager_id}`}
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Open
          </Link>
        </div>
      </div>
    );
  }

  return (
    <form action={action} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm font-medium">
        Goal
        <textarea
          name="goal"
          required
          minLength={10}
          maxLength={500}
          rows={3}
          placeholder="e.g. Ship the v1 of the side project by Friday and post it publicly."
          className="resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
        />
        <span className="text-xs text-muted-foreground">
          Be specific. Vague goals lose. &quot;Get fit&quot; is not a goal — &quot;Run 4x/week
          for 6 weeks, logged on Strava&quot; is.
        </span>
      </label>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Start
          <input
            name="start_at"
            type="date"
            required
            defaultValue={todayISO()}
            min={todayISO()}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          End
          <input
            name="end_at"
            type="date"
            required
            defaultValue={nDaysFromTodayISO(14)}
            min={nDaysFromTodayISO(1)}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
          />
        </label>
      </div>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Stake (USD)
        <input
          name="stake_cents"
          type="hidden"
          value={Math.round(Number(stakeDollars) * 100)}
        />
        <input
          type="number"
          min={minStake / 100}
          max={maxStake / 100}
          step="1"
          value={stakeDollars}
          onChange={(e) => setStakeDollars(e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
        />
        <span className="text-xs text-muted-foreground">
          Min ${(minStake / 100).toFixed(2)}, max ${(maxStake / 100).toFixed(2)} on your {tier} tier.
        </span>
      </label>

      <input type="hidden" name="currency" value="usd" />

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">Anti-charity</legend>
        <p className="text-xs text-muted-foreground">
          If you fail, your stake goes here. Pick the cause that would
          actually hurt to fund.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {antiCharities.map((c) => {
            const checked = acknowledgedCharity === c.slug;
            return (
              <label
                key={c.slug}
                className={`flex cursor-pointer flex-col gap-1 rounded-md border border-input bg-background p-3 text-sm shadow-sm ${
                  checked ? "border-primary bg-primary/5" : ""
                }`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="anti_charity_slug"
                    value={c.slug}
                    checked={checked}
                    onChange={() => setAcknowledgedCharity(c.slug)}
                  />
                  <span className="font-medium">{c.name}</span>
                </div>
                <span className="text-[11px] text-muted-foreground">{c.description}</span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Referee (optional, Pro/Max)
        <input
          name="referee_id"
          placeholder="Profile UUID — leave blank for AI evaluation"
          className="rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm"
        />
        <span className="text-xs text-muted-foreground">
          A human you trust to confirm whether you hit the goal. UI for
          picking by username ships with the §27 step 38-44 polish pass.
        </span>
      </label>

      {!polarEnabled && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
          Polar.sh integration isn&apos;t live yet — this is a dry run. The
          row writes to the database and the evaluator picks it up at
          end-date, but no money actually moves.
        </p>
      )}

      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">{state.error}</p>
      )}

      <button
        type="submit"
        disabled={pending || !acknowledgedCharity}
        className="self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Creating…" : polarEnabled ? "Stake and start" : "Start dry-run wager"}
      </button>
    </form>
  );
}
