"use client";

import { useState } from "react";

interface Props {
  text: string;
  label?: string;
}

export function CopyButton({ text, label = "Copy" }: Props) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* user denied or unavailable */
        }
      }}
      className="rounded-md border border-input bg-background px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground hover:bg-accent"
    >
      {copied ? "Copied" : label}
    </button>
  );
}
