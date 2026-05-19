"use client";

import { useFormState, useFormStatus } from "react-dom";
import {
  approvePersonaAction,
  rejectPersonaAction,
  type ActionResult,
} from "../actions";

interface Props {
  persona: {
    id: string;
    slug: string;
    name: string;
    category: string;
    system_prompt: string;
    created_at: string;
  };
}

const initialState: ActionResult | null = null;

export function PersonaRow({ persona }: Props) {
  const [approveState, approveAction] = useFormState(approvePersonaAction, initialState);
  const [rejectState, rejectAction] = useFormState(rejectPersonaAction, initialState);
  const lastError =
    (approveState && !approveState.ok && approveState.error) ||
    (rejectState && !rejectState.ok && rejectState.error) ||
    null;

  return (
    <article className="flex flex-col gap-3 rounded-md border border-input bg-card p-4 shadow-sm">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold">{persona.name}</h3>
          <p className="text-[11px] text-muted-foreground">
            <code>{persona.slug}</code> · {persona.category} ·{" "}
            {new Date(persona.created_at).toLocaleString()}
          </p>
        </div>
      </header>
      <details className="rounded-md border border-input bg-background px-3 py-2 text-xs">
        <summary className="cursor-pointer text-muted-foreground">View system prompt</summary>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs">
          {persona.system_prompt}
        </pre>
      </details>
      <div className="flex flex-wrap items-center gap-2">
        <form action={approveAction} className="contents">
          <input type="hidden" name="persona_id" value={persona.id} />
          <SubmitButton label="Approve" variant="primary" />
        </form>
        <form action={rejectAction} className="contents">
          <input type="hidden" name="persona_id" value={persona.id} />
          <input
            type="text"
            name="notes"
            placeholder="Optional notes"
            className="rounded-md border border-input bg-background px-2 py-1 text-xs"
          />
          <SubmitButton label="Reject" variant="destructive" />
        </form>
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
