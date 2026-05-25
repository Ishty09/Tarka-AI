"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

// Three-state toggle: light / dark / system. Renders the icon of the
// CURRENT resolved theme; click cycles light → dark → system → light.

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // next-themes hydration guard — avoid SSR/CSR mismatch on the icon.
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <button
        type="button"
        aria-label="Theme"
        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-input bg-background text-muted-foreground"
      >
        <span className="h-4 w-4" />
      </button>
    );
  }

  const current = theme ?? "system";
  const next =
    current === "light" ? "dark" : current === "dark" ? "system" : "light";

  const icon =
    resolvedTheme === "dark" ? (
      // moon
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    ) : (
      // sun
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
    );

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      title={`Theme: ${current} (click for ${next})`}
      aria-label={`Switch theme — currently ${current}`}
      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-input bg-background text-foreground transition hover:bg-accent"
    >
      {icon}
    </button>
  );
}
