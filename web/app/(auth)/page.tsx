import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AuthForm from "@/components/AuthForm/AuthForm";
import { apiGet } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { ProfileData } from "@/lib/types";

export const metadata: Metadata = { title: "Log in · OpenArt" };

// The home page: the login form for visitors. Logged-in artists go to Discover once they have
// saved their profile (the end of the onboarding), to the onboarding's Documents before that.
export default async function HomePage() {
    if (await getCurrentUser()) {
        const profile = await apiGet<ProfileData>("/api/profile");
        redirect(profile.updated_at ? "/discover" : "/documents");
    }
    return <AuthForm mode="login" />;
}
