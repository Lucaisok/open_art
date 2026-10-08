import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AuthForm from "@/components/AuthForm/AuthForm";
import { getCurrentUser } from "@/lib/session";

export const metadata: Metadata = { title: "Log in · OpenArt" };

export default async function LoginPage() {
    if (await getCurrentUser()) {
        redirect("/account");
    }
    return <AuthForm mode="login" />;
}
