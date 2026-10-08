import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AuthForm from "@/components/AuthForm/AuthForm";
import { getCurrentUser } from "@/lib/session";
import styles from "../auth-page.module.css";

export const metadata: Metadata = { title: "Log in · OpenArt" };

export default async function LoginPage() {
    if (await getCurrentUser()) {
        redirect("/account");
    }
    return (
        <main id="main" className={styles.main}>
            <h1 className={styles.title}>Log in</h1>
            <AuthForm mode="login" />
        </main>
    );
}
