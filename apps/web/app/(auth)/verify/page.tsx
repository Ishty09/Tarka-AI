// /verify is the landing page users hit if they tap an expired or already-used
// magic link. Supabase Auth surfaces the failure as a callback redirect to
// /login?error=..., so /verify is a manual checkpoint: tell the user the email
// is on its way and give them a path back.

interface PageProps {
  searchParams: Promise<{ email?: string }>;
}

export default async function VerifyPage({ searchParams }: PageProps) {
  const { email } = await searchParams;
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="mx-auto flex w-full max-w-sm flex-col gap-4 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Check your inbox</h1>
        <p className="text-sm text-muted-foreground">
          {email
            ? <>We sent a magic link to <span className="font-medium text-foreground">{email}</span>. It expires in 1 hour.</>
            : "We sent you a magic link. It expires in 1 hour."}
        </p>
        <p className="text-sm text-muted-foreground">
          Didn&apos;t get it? Check spam or <a href="/login" className="underline">try a different method</a>.
        </p>
      </div>
    </main>
  );
}
