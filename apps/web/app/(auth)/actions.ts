"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { trackServer } from "@/lib/analytics";
import { env } from "@/lib/env";
import { createServerSupabase } from "@/lib/supabase/server";

// Server actions for the (auth) route group. Each action:
//   1. Validates input against a zod schema (§1 rule 9).
//   2. Calls Supabase Auth via the SSR server client.
//   3. Redirects (success) or returns an error string (failure).
//
// We deliberately don't catch internal errors and pretend success — auth
// failures must surface to the user so they can retry or switch method.

export type AuthActionResult = { ok: true } | { ok: false; error: string };

// ----- Magic link -----------------------------------------------------------

const magicLinkSchema = z.object({
  email: z.string().email(),
  next: z.string().optional(),
});

export async function signInWithMagicLink(_prev: AuthActionResult | null, formData: FormData): Promise<AuthActionResult> {
  const parsed = magicLinkSchema.safeParse({
    email: formData.get("email"),
    next: formData.get("next") ?? undefined,
  });
  if (!parsed.success) {
    return { ok: false, error: "Enter a valid email address." };
  }

  const supabase = await createServerSupabase();
  const emailRedirectTo = buildCallbackUrl(parsed.data.next ?? "/chat");

  const { error } = await supabase.auth.signInWithOtp({
    email: parsed.data.email,
    options: { emailRedirectTo },
  });

  if (error) return { ok: false, error: error.message };

  // §20 signup_started — fires when a user requests a magic link. We
  // can't tell apart "new" vs "returning" until callback, so this name
  // covers both paths; the callback fires signup_completed once the
  // session is established.
  await trackServer("signup_started", { method: "magic_link" });
  return { ok: true };
}

// ----- OAuth start ----------------------------------------------------------

const oauthSchema = z.object({
  provider: z.enum(["google", "apple"]),
  next: z.string().optional(),
});

export async function signInWithOAuth(formData: FormData): Promise<never> {
  const parsed = oauthSchema.safeParse({
    provider: formData.get("provider"),
    next: formData.get("next") ?? undefined,
  });
  if (!parsed.success) {
    // Unknown provider — bounce back to login. Caller should never hit this
    // unless the form was tampered with.
    redirect("/login?error=invalid_provider");
  }

  const supabase = await createServerSupabase();
  const redirectTo = buildCallbackUrl(parsed.data.next ?? "/chat");

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: parsed.data.provider,
    options: {
      redirectTo,
      // §1 rule 7 — no client-side secrets. Scopes are explicit so we don't
      // accidentally request more than we need from Google / Apple.
      scopes: parsed.data.provider === "google" ? "openid email profile" : "name email",
    },
  });

  if (error || !data?.url) {
    redirect(`/login?error=${encodeURIComponent(error?.message ?? "oauth_failed")}`);
  }
  await trackServer("signup_started", { method: parsed.data.provider });
  redirect(data.url);
}

// ----- Signout --------------------------------------------------------------

export async function signOut(): Promise<never> {
  const supabase = await createServerSupabase();
  await supabase.auth.signOut();
  redirect("/login");
}

// ----- Helpers --------------------------------------------------------------

function buildCallbackUrl(nextPath: string): string {
  // OAuth + magic link both land on /auth/callback?code=...&next=...
  const url = new URL("/auth/callback", env.NEXT_PUBLIC_APP_URL);
  url.searchParams.set("next", sanitizeNext(nextPath));
  return url.toString();
}

function sanitizeNext(next: string): string {
  // Open-redirect guard: only allow same-origin relative paths.
  if (!next.startsWith("/") || next.startsWith("//")) return "/chat";
  return next;
}
