import { redirect } from "next/navigation";

// Auth removed — this is a no-auth self-hosted tool.
// Redirect to dashboard directly.
export default function SignInPage() {
  redirect("/dashboard");
}
