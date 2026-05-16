"use client";

import { createBrowserClient } from "@supabase/ssr";

// Client-side Supabase client. Reads NEXT_PUBLIC_* at module load — those are
// inlined at build time, no runtime env access needed.

export function createBrowserSupabase() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
