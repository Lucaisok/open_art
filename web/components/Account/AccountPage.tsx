"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { sendJson } from "@/lib/api";
import { forgetSearch } from "@/lib/discover";
import LogoutButton from "@/components/ProfileEditor/LogoutButton";
import { useToast } from "@/components/ui/Toast";
import buttons from "@/components/ui/buttons.module.css";
import styles from "./AccountPage.module.css";

const MIN_PASSWORD = 10;   // api/security.py MIN_PASSWORD_LENGTH

// The Account page (design: STUDIO.md → Account): who is logged in with Log out, change password
// (it logs out every other browser: api/account.py), what happens to the artist's data, and
// deleting the account, permanent, so it asks for the password first.
const AccountPage = ({ email }: { email: string }) => {
    const router = useRouter();
    const toast = useToast();
    const [passwordError, setPasswordError] = useState<string | null>(null);
    const [changing, setChanging] = useState(false);
    const [deletePassword, setDeletePassword] = useState("");
    const [deleteError, setDeleteError] = useState<string | null>(null);
    const [deleting, setDeleting] = useState(false);

    const changePassword = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        const next = String(data.get("new") ?? "");
        if (next.length < MIN_PASSWORD) {
            setPasswordError(`The new password must be at least ${MIN_PASSWORD} characters long.`);
            return;
        }
        if (next !== data.get("repeat")) {
            setPasswordError("The two new passwords are different.");
            return;
        }
        setChanging(true);
        setPasswordError(null);
        const result = await sendJson("POST", "/api/account/password", { current_password: data.get("current"), new_password: next });
        setChanging(false);
        if (!result.ok) {
            setPasswordError(result.error);
            return;
        }
        form.reset();
        toast("Password updated");
    };

    const deleteAccount = async (event: FormEvent) => {
        event.preventDefault();
        setDeleting(true);
        setDeleteError(null);
        const result = await sendJson("DELETE", "/api/account", { password: deletePassword });
        if (!result.ok) {
            setDeleting(false);
            setDeleteError(result.error);
            return;
        }
        forgetSearch();
        router.push("/");
        router.refresh();
    };

    return (
        <main id="main" className={styles.main}>
            <h1 className={styles.title}>Account</h1>

            <section aria-labelledby="h-login" className={styles.login}>
                <div className={styles.loginText}>
                    <h2 id="h-login" className={styles.mutedHeading}>Logged in as</h2>
                    <span className={styles.email}>{email}</span>
                </div>
                <LogoutButton className={styles.logout} />
            </section>

            <section aria-labelledby="h-password" className={styles.section}>
                <h2 id="h-password" className={styles.heading}>Change password</h2>
                <form className={styles.passwordForm} onSubmit={changePassword} noValidate>
                    <div className={styles.passwordFields}>
                        <label className={styles.field}>
                            <span className={styles.label}>Current password</span>
                            <input name="current" type="password" autoComplete="current-password" className={styles.input} required />
                        </label>
                        <label className={styles.field}>
                            <span className={styles.label}>New password</span>
                            <input name="new" type="password" autoComplete="new-password" className={styles.input} required
                                   aria-describedby="password-hint" />
                        </label>
                        <label className={styles.field}>
                            <span className={styles.label}>Repeat new password</span>
                            <input name="repeat" type="password" autoComplete="new-password" className={styles.input} required />
                        </label>
                    </div>
                    <span id="password-hint" className={styles.hint}>At least {MIN_PASSWORD} characters.</span>
                    {passwordError && <p role="alert" className={buttons.error}>{passwordError}</p>}
                    <button type="submit" className={`${buttons.dark} ${styles.submit}`} disabled={changing}>
                        {changing ? "Updating…" : "Update password"}
                    </button>
                </form>
            </section>

            <section aria-labelledby="h-data" className={styles.section}>
                <h2 id="h-data" className={styles.heading}>Your data</h2>
                <p className={styles.text}>
                    Your documents and images stay on OpenArt&apos;s server. Only drafting sends passages from your
                    documents to OpenAI, to write answers for the call you&apos;re drafting.
                </p>
            </section>

            <section aria-labelledby="h-delete" className={styles.danger}>
                <h2 id="h-delete" className={styles.dangerHeading}>Delete account</h2>
                <p className={styles.dangerText}>Permanently deletes your account, profile, documents, projects and images.</p>
                <form onSubmit={deleteAccount} className={styles.deleteForm}>
                    <label className={`${styles.field} ${styles.deleteField}`}>
                        <span className={styles.label}>Enter your password to confirm</span>
                        <input type="password" autoComplete="current-password" className={styles.input} value={deletePassword}
                               onChange={(e) => setDeletePassword(e.target.value)} />
                    </label>
                    {deleteError && <p role="alert" className={buttons.error}>{deleteError}</p>}
                    <button type="submit" className={styles.deleteButton} disabled={!deletePassword || deleting}>
                        {deleting ? "Deleting…" : "Delete my account"}
                    </button>
                </form>
            </section>
        </main>
    );
};

export default AccountPage;
