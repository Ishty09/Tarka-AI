import { redirect } from "next/navigation";
import { AuthForm } from "../_components/AuthForm";
import { createServerSupabase } from "@/lib/supabase/server";

// Already-signed-in users skip the form. The middleware will catch the
// (app)/* gate; this is just a courtesy.

interface PageProps {
  searchParams: Promise<{ next?: string; error?: string }>;
}

export default async function LoginPage({ searchParams }: PageProps) {
  const { next, error } = await searchParams;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (user) redirect(next ?? "/chat");

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <AuthForm mode="login" next={next} errorMessage={error ? decodeURIComponent(error) : null} />
    </main>
  );
}
