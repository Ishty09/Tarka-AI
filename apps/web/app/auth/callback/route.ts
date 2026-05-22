import { type NextRequest, NextResponse } from "next/server";
import { hashUserId, trackServer } from "@/lib/analytics";
import { createServerSupabase } from "@/lib/supabase/server";

// OAuth + magic-link callback. Supabase issues a `code` in the URL; we
// exchange it for a session via the SSR client (which writes the cookies).
// On success we redirect to `next` if it's a safe same-origin path, otherwise
// /chat. Onboarding interception happens once the profile row is reachable
// (Phase A step 7 will wire `profiles.onboarding_completed_at` into this).

const SAFE_DEFAULT = "/chat";

export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const code = searchParams.get("code");
  const nextParam = searchParams.get("next") ?? SAFE_DEFAULT;
  const next = nextParam.startsWith("/") && !nextParam.startsWith("//") ? nextParam : SAFE_DEFAULT;

  if (!code) {
    return NextResponse.redirect(`${origin}/login?error=missing_code`);
  }

  const supabase = await createServerSupabase();
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(error.message)}`);
  }

  // §20 signup_completed fires once the session is established. This
  // covers both genuinely-new signups and returning logins; the worker
  // can disambiguate by checking profiles.created_at server-side if
  // funnel reports need it.
  await trackServer("signup_completed", {
    user_id: hashUserId(data.user?.id ?? undefined),
  });

  return NextResponse.redirect(`${origin}${next}`);
}
