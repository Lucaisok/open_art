"use client";

import { useState, type FormEvent } from "react";
import Button from "@/components/Button/Button";
import FormMessage from "@/components/FormMessage/FormMessage";
import TextField from "@/components/TextField/TextField";
import { sendJson } from "@/lib/api";
import styles from "./AccountSettings.module.css";

const ChangePasswordForm = () => {
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [pending, setPending] = useState(false);

    const submit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        setPending(true);
        setError(null);
        setSuccess(null);
        const result = await sendJson("POST", "/api/account/password", {
            current_password: form.get("current_password"),
            new_password: form.get("new_password"),
        });
        setPending(false);
        if (!result.ok) {
            setError(result.error);
            return;
        }
        formElement.reset();
        setSuccess("Password changed. Other browsers where you were logged in have been logged out.");
    };

    return (
        <section aria-labelledby="change-password-title" className={styles.section}>
            <h2 id="change-password-title" className={styles.sectionTitle}>
                Change password
            </h2>
            <form onSubmit={submit} className={styles.form}>
                <FormMessage error={error} success={success} />
                <TextField
                    label="Current password"
                    name="current_password"
                    type="password"
                    autoComplete="current-password"
                    maxLength={200}
                    required
                />
                <TextField
                    label="New password"
                    name="new_password"
                    type="password"
                    autoComplete="new-password"
                    hint="At least 10 characters."
                    minLength={10}
                    maxLength={200}
                    required
                />
                <Button type="submit" disabled={pending}>
                    {pending ? "Saving…" : "Change password"}
                </Button>
            </form>
        </section>
    );
};

export default ChangePasswordForm;
