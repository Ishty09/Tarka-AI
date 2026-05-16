import { redirect } from "next/navigation";
import { AuthForm } from "../_components/AuthForm";
import { createServerSupabase } from "@/lib/supabase/server";

interface PageProps {
  searchParams: Promise<{ next?: string; error?: string }>;
}

export default async function SignupPage({ searchParams }: PageProps) {
  const { next, error } = await searchParams;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  // First sign-in goes through onboarding (Phase A step 7 will set
  // profiles.onboarding_completed_at and bounce completed users to /chat).
  if (user) redirect(next ?? "/onboarding");

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <AuthForm mode="signup" next={next} errorMessage={error ? decodeURIComponent(error) : null} />
    </main>
  );
}
