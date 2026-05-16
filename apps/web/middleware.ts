import type { NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

export function middleware(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  // Run on all paths except static assets + Next internals. Auth-cookie refresh
  // is best-effort: even public pages benefit from a fresh JWT so a logged-in
  // user clicking "/login" lands on the redirect-to-chat path instead.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|css|js|map|txt)$).*)",
  ],
};
