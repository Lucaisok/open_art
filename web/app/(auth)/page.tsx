import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AuthForm from "@/components/AuthForm/AuthForm";
import { getCurrentUser } from "@/lib/session";

export const metadata: Metadata = { title: "Log in · OpenArt" };

// The home page: the login form for visitors, the documents page for logged-in artists
export default async function HomePage() {
    if (await getCurrentUser()) {
        redirect("/documents");
    }
    return <AuthForm mode="login" />;
}
