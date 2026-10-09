import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AuthForm from "@/components/AuthForm/AuthForm";
import { getCurrentUser } from "@/lib/session";

export const metadata: Metadata = { title: "Sign up · OpenArt" };

export default async function SignupPage() {
    if (await getCurrentUser()) {
        redirect("/"); // already logged in: home decides (Discover or the onboarding)
    }
    return <AuthForm mode="signup" />;
}
