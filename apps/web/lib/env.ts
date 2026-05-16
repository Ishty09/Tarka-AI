// Server-side env access. Throws at module load if a required key is missing
// — preferable to a broken flow at first request. NEXT_PUBLIC_* are inlined
// at build time and don't need this gate.
//
// Server-only secrets (WORKERS_INTERNAL_SECRET) are NOT required at module
// load because dev sometimes runs without workers up; the chat-stream route
// re-checks at request time.

import { z } from "zod";

const requiredSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.string().url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1),
  NEXT_PUBLIC_APP_URL: z.string().url(),
});

const parsed = requiredSchema.safeParse({
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL,
});

if (!parsed.success) {
  const missing = parsed.error.issues.map((i) => i.path.join(".")).join(", ");
  throw new Error(`Missing or invalid env: ${missing}`);
}

export const env = parsed.data;

// Server-only fields. Accessed lazily — see chat-stream route.

export const serverEnv = {
  WORKERS_URL: process.env.WORKERS_URL ?? "http://localhost:8000",
  WORKERS_INTERNAL_SECRET: process.env.WORKERS_INTERNAL_SECRET ?? "",
} as const;
