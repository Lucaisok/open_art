import type { Metadata } from "next";
import { redirect } from "next/navigation";
import ChangePasswordForm from "@/components/AccountSettings/ChangePasswordForm";
import DeleteAccount from "@/components/AccountSettings/DeleteAccount";
import { getCurrentUser } from "@/lib/session";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Your account · OpenArt" };

const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

export default async function AccountPage() {
    const user = await getCurrentUser();
    if (!user) {
        redirect("/"); // private page: logged-out visitors go to the login form (the home page)
    }
    return (
        <main id="main" className={styles.main}>
            <h1 className={styles.title}>Your account</h1>
            <p className={styles.meta}>
                Logged in as <strong>{user.email}</strong> · member since {formatDate(user.created_at)}
            </p>
            <ChangePasswordForm />
            <DeleteAccount />
        </main>
    );
}
