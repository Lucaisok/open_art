"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import Button from "@/components/Button/Button";
import FormMessage from "@/components/FormMessage/FormMessage";
import TextField from "@/components/TextField/TextField";
import { sendJson } from "@/lib/api";
import styles from "./AuthForm.module.css";

type AuthFormProps = {
    mode: "login" | "signup";
};

// One form for both pages: they ask for the same two fields, only the endpoint and wording differ
const AuthForm = ({ mode }: AuthFormProps) => {
    const router = useRouter();
    const [error, setError] = useState<string | null>(null);
    const [pending, setPending] = useState(false);
    const isSignup = mode === "signup";

    const submit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setPending(true);
        setError(null);
        const result = await sendJson("POST", `/api/auth/${mode}`, {
            email: form.get("email"),
            password: form.get("password"),
        });
        if (!result.ok) {
            setError(result.error);
            setPending(false);
            return;
        }
        router.push("/account");
        router.refresh(); // re-render the header with the user
    };

    return (
        <form onSubmit={submit} className={styles.form}>
            <FormMessage error={error} />
            <TextField label="Email" name="email" type="email" autoComplete="email" required />
            <TextField
                label="Password"
                name="password"
                type="password"
                autoComplete={isSignup ? "new-password" : "current-password"}
                hint={isSignup ? "At least 10 characters. A few words together make a strong password." : undefined}
                minLength={isSignup ? 10 : undefined}
                maxLength={200}
                required
            />
            <Button type="submit" disabled={pending}>
                {pending ? "Please wait…" : isSignup ? "Create account" : "Log in"}
            </Button>
            <p className={styles.switch}>
                {isSignup ? (
                    <>
                        Already have an account? <Link href="/login">Log in</Link>
                    </>
                ) : (
                    <>
                        New to OpenArt? <Link href="/signup">Create an account</Link>
                    </>
                )}
            </p>
        </form>
    );
};

export default AuthForm;
