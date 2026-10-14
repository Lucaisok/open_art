import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AuthForm from "@/components/AuthForm/AuthForm";
import { getCurrentUser } from "@/lib/session";

export const metadata: Metadata = { title: "Log in · OpenArt" };

// The home page: the login form for visitors. Logged-in artists go to Discover once they finished
// the onboarding, to its first step (Documents) before that.
export default async function HomePage() {
    const user = await getCurrentUser();
    if (user) {
        redirect(user.onboarded_at ? "/discover" : "/documents");
    }
    return <AuthForm mode="login" />;
}
