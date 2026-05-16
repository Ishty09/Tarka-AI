import { type NextRequest, NextResponse } from "next/server";
import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { env } from "../env";

// Per supabase/ssr docs, the middleware must:
//   1. Build a response we can mutate cookies on.
//   2. Run getUser() so the SDK refreshes the JWT if it's near expiry.
//   3. Mirror any cookie changes back onto BOTH the request and response.
//
// (auth)/* routes are public — login/signup/verify. (app)/* requires a session;
// missing session redirects to /login with the original path captured in `next`.

const PUBLIC_PREFIXES = ["/", "/login", "/signup", "/verify", "/auth", "/legal", "/pricing", "/about", "/roast", "/argue"];
const APP_PREFIXES = ["/chat", "/personas", "/couples", "/groups", "/wagers", "/contradictions", "/mirror", "/eulogy", "/feed", "/tools", "/settings", "/onboarding"];

export async function updateSession(request: NextRequest): Promise<NextResponse> {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
          for (const { name, value } of cookiesToSet) {
            request.cookies.set(name, value);
          }
          response = NextResponse.next({ request });
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;
  const requiresAuth = APP_PREFIXES.some((p) => path === p || path.startsWith(`${p}/`));

  if (requiresAuth && !user) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", path);
    return NextResponse.redirect(url);
  }

  // Lightweight tag so callers know whether we considered the path public.
  // Not currently consumed but cheap and useful in dev.
  void PUBLIC_PREFIXES;
  return response;
}
