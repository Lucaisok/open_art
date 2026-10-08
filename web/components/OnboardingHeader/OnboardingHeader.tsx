"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./OnboardingHeader.module.css";

// The onboarding steps, in order. Account is the sign-up the artist already did; its
// pill links to /account (password, log out, delete account).
const STEPS = [
    { label: "Account", href: "/account" },
    { label: "Documents", href: "/documents" },
    { label: "Profile", href: "/profile" },
];

// Black bar on the onboarding pages: the wordmark and the three steps as pills
// (done / current / upcoming, design: design_handoff_openart 2, DOCUMENTS.md → Header)
const OnboardingHeader = () => {
    const pathname = usePathname();
    const current = STEPS.findIndex((step) => pathname.startsWith(step.href));

    return (
        <header className={styles.header}>
            <Link href="/documents" className={styles.wordmark}>
                OpenArt
            </Link>
            <nav aria-label="Onboarding steps">
                <ol className={styles.steps}>
                    {STEPS.map((step, i) => {
                        const state = i < current ? styles.done : i === current ? styles.current : styles.upcoming;
                        const text = `${i + 1}  ${step.label}`; // two non-breaking spaces, as in the design
                        return (
                            <li key={step.href}>
                                {i === current ? (
                                    <span className={`${styles.pill} ${state}`} aria-current="step">
                                        {text}
                                    </span>
                                ) : (
                                    <Link href={step.href} className={`${styles.pill} ${state}`}>
                                        {text}
                                    </Link>
                                )}
                            </li>
                        );
                    })}
                </ol>
            </nav>
        </header>
    );
};

export default OnboardingHeader;
