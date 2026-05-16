import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase/server";
import { env } from "@/lib/env";

// POST-only signout endpoint. Form posts here from the user menu in (app)/*.
// Kept as a route handler (not a server action) so non-React contexts — like
// a signout link embedded in an email — also work.

export async function POST() {
  const supabase = await createServerSupabase();
  await supabase.auth.signOut();
  return NextResponse.redirect(new URL("/login", env.NEXT_PUBLIC_APP_URL), { status: 303 });
}
