"use client";

import { useActionState } from "react";
import { signInWithMagicLink, type AuthActionResult } from "../actions";

// Shared form for /login and /signup. Behaviour is identical — Supabase Auth
// magic links auto-create the user on first send — so we expose one component
// and let the page choose the copy. Google + Apple are plain <form> POSTs to
// the OAuth server action so they work even with JS disabled.

interface Props {
  mode: "login" | "signup";
  next?: string;
  errorMessage?: string | null;
}

export function AuthForm({ mode, next, errorMessage }: Props) {
  const [state, formAction, pending] = useActionState<AuthActionResult | null, FormData>(
    signInWithMagicLink,
    null,
  );

  const heading = mode === "login" ? "Sign in" : "Create your account";
  const subline =
    mode === "login"
      ? "Magic link, Google, or Apple. No passwords on file."
      : "Pick a sign-in method. We never store passwords.";

  return (
    <div className="mx-auto flex w-full max-w-sm flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{heading}</h1>
        <p className="text-sm text-muted-foreground">{subline}</p>
      </header>

      {errorMessage && (
        <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errorMessage}
        </p>
      )}

      <div className="flex flex-col gap-2">
        <OAuthButton provider="google" next={next} label="Continue with Google" />
        <OAuthButton provider="apple" next={next} label="Continue with Apple" />
      </div>

      <div className="relative">
        <div className="absolute inset-0 flex items-center"><span className="w-full border-t" /></div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-background px-2 text-muted-foreground">or</span>
        </div>
      </div>

      <form action={formAction} className="flex flex-col gap-3">
        {next && <input type="hidden" name="next" value={next} />}
        <label htmlFor="email" className="text-sm font-medium">Email</label>
        <input
          id="email"
          name="email"
          type="email"
          required
          autoComplete="email"
          inputMode="email"
          placeholder="you@example.com"
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <button
          type="submit"
          disabled={pending}
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm transition hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Sending..." : "Email me a magic link"}
        </button>

        {state?.ok === true && (
          <p role="status" className="text-sm text-muted-foreground">
            Check your inbox. The link expires in 1 hour.
          </p>
        )}
        {state?.ok === false && (
          <p role="alert" className="text-sm text-destructive">{state.error}</p>
        )}
      </form>

      <p className="text-center text-xs text-muted-foreground">
        By continuing you agree to the <a href="/legal/terms/en" className="underline">Terms</a> and{" "}
        <a href="/legal/privacy/en" className="underline">Privacy Policy</a>.
      </p>
    </div>
  );
}

function OAuthButton({ provider, next, label }: { provider: "google" | "apple"; next?: string; label: string }) {
  return (
    <form action="/auth/oauth" method="post">
      <input type="hidden" name="provider" value={provider} />
      {next && <input type="hidden" name="next" value={next} />}
      <button
        type="submit"
        className="inline-flex w-full items-center justify-center rounded-md border border-input bg-background px-3 py-2 text-sm font-medium shadow-sm transition hover:bg-accent hover:text-accent-foreground"
      >
        {label}
      </button>
    </form>
  );
}
