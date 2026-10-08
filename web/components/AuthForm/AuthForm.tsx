"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { sendJson } from "@/lib/api";
import styles from "./AuthForm.module.css";

type AuthFormProps = {
    mode: "login" | "signup";
};

// Must match the API (api/auth.py): shorter passwords are refused at sign-up
const MIN_PASSWORD_LENGTH = 10;

// Everything the two pages say differently
const TEXT = {
    login: {
        heading: "Welcome back.",
        subheading: "Your feed and applications are where you left them.",
        placeholder: "Your password",
        cta: "Log in",
        switchPrompt: "New to OpenArt?",
        switchLink: "Create an account",
        switchHref: "/signup",
    },
    signup: {
        heading: "Make an account.",
        subheading: "Two fields. Your artist profile comes next.",
        placeholder: `At least ${MIN_PASSWORD_LENGTH} characters`,
        cta: "Create account",
        switchPrompt: "Already have an account?",
        switchLink: "Log in",
        switchHref: "/",
    },
};

// One form for both pages: they ask for the same two fields, only the endpoint and wording differ.
// The Log in / Sign up switch links to the other page (/ is the login form, /signup), so each has its own URL.
const AuthForm = ({ mode }: AuthFormProps) => {
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [pending, setPending] = useState(false);
    const isSignup = mode === "signup";
    const text = TEXT[mode];

    // The same checks as the API, so most mistakes are caught before a request is sent
    const validate = (): string | null => {
        if (!/^\S+@\S+\.\S+$/.test(email)) {
            return "Enter a valid email address.";
        }
        if (isSignup && password.length < MIN_PASSWORD_LENGTH) {
            return `Password needs at least ${MIN_PASSWORD_LENGTH} characters.`;
        }
        if (!isSignup && !password) {
            return "Enter your password.";
        }
        return null;
    };

    const submit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const problem = validate();
        if (problem) {
            setError(problem);
            return;
        }
        setPending(true);
        setError(null);
        const result = await sendJson("POST", `/api/auth/${mode}`, { email, password });
        if (!result.ok) {
            setError(result.error);
            setPending(false);
            return;
        }
        // both go to the documents page for now (the design's onboarding). Later: login → the feed
        router.push("/documents");
        router.refresh();
    };

    return (
        <>
            {/* Log in / Sign up switch: links styled as two tabs, the current page highlighted */}
            <nav aria-label="Log in or sign up" className={styles.switcher}>
                <Link
                    href="/"
                    className={styles.tab}
                    aria-current={isSignup ? undefined : "page"}
                >
                    Log in
                </Link>
                <Link
                    href="/signup"
                    className={styles.tab}
                    aria-current={isSignup ? "page" : undefined}
                >
                    Sign up
                </Link>
            </nav>

            <h1 className={styles.heading}>{text.heading}</h1>
            <p className={styles.subheading}>{text.subheading}</p>

            {/* noValidate: our own messages (in the error box) replace the browser's bubbles */}
            <form onSubmit={submit} className={styles.form} noValidate>
                <div className={styles.field}>
                    <label htmlFor="auth-email" className={styles.label}>
                        Email
                    </label>
                    <input
                        id="auth-email"
                        name="email"
                        type="email"
                        autoComplete="email"
                        placeholder="you@studio.com"
                        className={styles.input}
                        value={email}
                        onChange={(event) => {
                            setEmail(event.target.value);
                            setError(null); // typing clears the error
                        }}
                        required
                    />
                </div>

                <div className={styles.field}>
                    <label htmlFor="auth-password" className={styles.label}>
                        Password
                    </label>
                    <div className={styles.passwordWrap}>
                        <input
                            id="auth-password"
                            name="password"
                            type={showPassword ? "text" : "password"}
                            autoComplete={isSignup ? "new-password" : "current-password"}
                            placeholder={text.placeholder}
                            className={`${styles.input} ${styles.passwordInput}`}
                            value={password}
                            onChange={(event) => {
                                setPassword(event.target.value);
                                setError(null);
                            }}
                            maxLength={200}
                            required
                        />
                        <button
                            type="button"
                            className={styles.toggle}
                            onClick={() => setShowPassword(!showPassword)}
                        >
                            {showPassword ? "Hide" : "Show"}
                            <span className={styles.visuallyHidden}> password</span>
                        </button>
                    </div>
                </div>

                {error && (
                    <p role="alert" className={styles.error}>
                        {error}
                    </p>
                )}

                <button type="submit" className={styles.submit} disabled={pending}>
                    <span>{pending ? "Please wait…" : text.cta}</span>
                    <span className={styles.arrow} aria-hidden="true">
                        →
                    </span>
                </button>
            </form>

            <p className={styles.switchLine}>
                {text.switchPrompt} <Link href={text.switchHref}>{text.switchLink}</Link>
            </p>

            {isSignup && (
                <p className={styles.legal}>
                    By creating an account you agree to the terms and privacy policy.
                </p>
            )}
        </>
    );
};

export default AuthForm;
