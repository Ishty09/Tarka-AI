import { cookies } from "next/headers";
import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { env } from "../env";

// Server-side Supabase client for Server Components, Server Actions, and
// Route Handlers. Uses the request's cookie store so reads run as the signed-in
// user (RLS — §6.7 — enforces every policy from there).
//
// Per CLAUDE.md §1.3: the service-role key NEVER lives in apps/web. If a job
// needs to bypass RLS, it runs in apps/workers.

export async function createServerSupabase() {
  const cookieStore = await cookies();
  return createServerClient(env.NEXT_PUBLIC_SUPABASE_URL, env.NEXT_PUBLIC_SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
        // In Server Components this throws; in Server Actions / Route Handlers
        // it succeeds. The supabase/ssr docs recommend swallowing the error to
        // let the middleware (which always runs) be the authoritative writer.
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          /* set from Server Component — middleware will refresh on next req */
        }
      },
    },
  });
}
