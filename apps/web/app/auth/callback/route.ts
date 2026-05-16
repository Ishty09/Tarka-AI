import { type NextRequest, NextResponse } from "next/server";
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
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(error.message)}`);
  }

  return NextResponse.redirect(`${origin}${next}`);
}
