"use client";

import { useActionState, useState } from "react";
import { LOCALES, PERSONA_SYSTEM_PROMPT_MAX_CHARS } from "@quarrel/shared/constants";
import { createPersona, type ActionResult } from "./actions";

const CATEGORIES = [
  { value: "argue", label: "Argue" },
  { value: "roast", label: "Roast" },
  { value: "mediate", label: "Mediate" },
  { value: "council", label: "Council" },
  { value: "productivity", label: "Productivity" },
  { value: "cultural", label: "Cultural" },
] as const;

export function CreatePersonaForm({ defaultLocale }: { defaultLocale: string }) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(createPersona, null);
  const [promptLen, setPromptLen] = useState(0);

  return (
    <form action={action} className="flex flex-col gap-3">
      <label htmlFor="name" className="text-sm font-medium">Name</label>
      <input
        id="name"
        name="name"
        required
        minLength={2}
        maxLength={60}
        placeholder="e.g. Brutal Career Advisor"
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
      />

      <label htmlFor="description" className="text-sm font-medium">Short description</label>
      <input
        id="description"
        name="description"
        required
        minLength={10}
        maxLength={500}
        placeholder="What does this persona do, and to whom?"
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="category" className="text-sm font-medium">Category</label>
          <select
            id="category"
            name="category"
            defaultValue="argue"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="locale" className="text-sm font-medium">Locale</label>
          <select
            id="locale"
            name="locale"
            defaultValue={defaultLocale}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
          >
            {LOCALES.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>
      </div>

      <label htmlFor="system_prompt" className="text-sm font-medium">
        System prompt
        <span className="ml-2 text-xs text-muted-foreground">
          {promptLen} / {PERSONA_SYSTEM_PROMPT_MAX_CHARS}
        </span>
      </label>
      <textarea
        id="system_prompt"
        name="system_prompt"
        required
        minLength={50}
        maxLength={PERSONA_SYSTEM_PROMPT_MAX_CHARS}
        rows={10}
        onChange={(e) => setPromptLen(e.target.value.length)}
        placeholder="Voice, speech patterns, references. Don't repeat the anti-sycophant rules — they're layered in automatically."
        className="rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm"
      />

      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">{state.error}</p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="mt-2 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Creating..." : "Create persona"}
      </button>
    </form>
  );
}
