import { signInWithOAuth } from "@/app/(auth)/actions";

// POST endpoint hit by the AuthForm's OAuth buttons. Server action handles
// the redirect to the provider — we just forward the FormData.

export async function POST(request: Request) {
  const formData = await request.formData();
  return signInWithOAuth(formData);
}
