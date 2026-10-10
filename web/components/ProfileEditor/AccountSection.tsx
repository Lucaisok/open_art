"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { sendJson } from "@/lib/api";
import { forgetSearch } from "@/lib/discover";
import LogoutButton from "./LogoutButton";
import styles from "./AccountSection.module.css";

// The Account box at the bottom of the profile (there is no account page): who is logged in with
// Log out, then Delete account. Deleting is permanent, so it asks again in a dialog, with the
// password. The native <dialog> opened with showModal() keeps keyboard focus inside it, closes on
// Escape and hides the rest of the page from screen readers.
const AccountSection = ({ email }: { email: string }) => {
    const router = useRouter();
    const dialogRef = useRef<HTMLDialogElement>(null);
    const [error, setError] = useState<string | null>(null);
    const [pending, setPending] = useState(false);

    const close = () => {
        setError(null);
        dialogRef.current?.close();
    };

    const submit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setPending(true);
        setError(null);
        const result = await sendJson("DELETE", "/api/account", { password: form.get("password") });
        if (!result.ok) {
            setError(result.error);
            setPending(false);
            return;
        }
        forgetSearch();
        router.push("/");
        router.refresh();
    };

    return (
        <section aria-labelledby="account-title" className={styles.section}>
            <h2 id="account-title" className={styles.heading}>
                Account
            </h2>

            <div className={styles.row}>
                <div>
                    <h3 className={styles.title}>Logged in</h3>
                    <p className={styles.text}>
                        as <strong className={styles.email}>{email}</strong>
                    </p>
                </div>
                <LogoutButton className={styles.cancelButton} />
            </div>

            <div className={styles.row}>
                <div>
                    <h3 className={styles.title}>Delete account</h3>
                    <p className={styles.text}>
                        Permanently deletes your account, your profile and your documents. It can&apos;t be undone.
                    </p>
                </div>
                <button type="button" className={styles.dangerButton} onClick={() => dialogRef.current?.showModal()}>
                    Delete my account
                </button>
            </div>

            <dialog ref={dialogRef} aria-labelledby="delete-dialog-title" className={styles.dialog} onClose={close}>
                <form onSubmit={submit} className={styles.form}>
                    <h2 id="delete-dialog-title" className={styles.title}>
                        Delete your account?
                    </h2>
                    <p className={styles.text}>Enter your password to confirm.</p>
                    {error && (
                        <p role="alert" className={styles.error}>
                            {error}
                        </p>
                    )}
                    <label className={styles.label}>
                        Password
                        <input
                            name="password"
                            type="password"
                            autoComplete="current-password"
                            maxLength={200}
                            required
                            className={styles.input}
                        />
                    </label>
                    <div className={styles.actions}>
                        <button type="button" className={styles.cancelButton} onClick={close} disabled={pending}>
                            Cancel
                        </button>
                        <button type="submit" className={styles.dangerButton} disabled={pending}>
                            {pending ? "Deleting…" : "Delete permanently"}
                        </button>
                    </div>
                </form>
            </dialog>
        </section>
    );
};

export default AccountSection;
