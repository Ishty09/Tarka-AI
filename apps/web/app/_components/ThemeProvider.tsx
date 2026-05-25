"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ReactNode } from "react";

// Wraps every page so child components (ThemeToggle, useTheme()) work.
// `class` strategy matches our globals.css which uses `.dark` for the
// inverted palette. Default = system; user toggle persists in localStorage.

export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
