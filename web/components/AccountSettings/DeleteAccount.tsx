"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import Button from "@/components/Button/Button";
import FormMessage from "@/components/FormMessage/FormMessage";
import TextField from "@/components/TextField/TextField";
import { sendJson } from "@/lib/api";
import styles from "./AccountSettings.module.css";

// Deleting is permanent, so it asks again in a dialog, with the password.
// The native <dialog> opened with showModal() keeps keyboard focus inside it, closes on
// Escape and hides the rest of the page from screen readers: no library needed.
const DeleteAccount = () => {
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
        router.push("/");
        router.refresh();
    };

    return (
        <section aria-labelledby="delete-account-title" className={styles.section}>
            <h2 id="delete-account-title" className={styles.sectionTitle}>
                Delete account
            </h2>
            <p className={styles.text}>
                This permanently deletes your account and everything stored with it. It can&apos;t be undone.
            </p>
            <div>
                <Button variant="danger" onClick={() => dialogRef.current?.showModal()}>
                    Delete my account
                </Button>
            </div>

            <dialog ref={dialogRef} aria-labelledby="delete-dialog-title" className={styles.dialog} onClose={close}>
                <form onSubmit={submit} className={styles.form}>
                    <h2 id="delete-dialog-title" className={styles.sectionTitle}>
                        Delete your account?
                    </h2>
                    <p className={styles.text}>Enter your password to confirm.</p>
                    <FormMessage error={error} />
                    <TextField
                        label="Password"
                        name="password"
                        type="password"
                        autoComplete="current-password"
                        maxLength={200}
                        required
                    />
                    <div className={styles.actions}>
                        <Button variant="secondary" onClick={close} disabled={pending}>
                            Cancel
                        </Button>
                        <Button variant="danger" type="submit" disabled={pending}>
                            {pending ? "Deleting…" : "Delete permanently"}
                        </Button>
                    </div>
                </form>
            </dialog>
        </section>
    );
};

export default DeleteAccount;
