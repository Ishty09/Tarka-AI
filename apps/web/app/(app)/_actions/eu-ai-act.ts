"use server";

import { cookies } from "next/headers";
import { EU_AI_ACT_COOKIE, EU_AI_ACT_COOKIE_TTL_SECONDS } from "@/lib/eu-ai-act";

// Server action invoked from the EuAiActModal "I understand" button.
// Sets a 1-year cookie containing the ack timestamp. The cookie is HTTP-only
// (we read it server-side only) and SameSite=Lax — the modal action submits
// from the same origin so this is sufficient.

export async function acknowledgeAiDisclosure(): Promise<void> {
  const store = await cookies();
  store.set({
    name: EU_AI_ACT_COOKIE,
    value: new Date().toISOString(),
    maxAge: EU_AI_ACT_COOKIE_TTL_SECONDS,
    path: "/",
    sameSite: "lax",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
  });
}
