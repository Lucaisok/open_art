"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./OnboardingHeader.module.css";

// The onboarding steps, in order (design: STUDIO.md → App structure). The last one ends in
// "Continue to Discover", after which these pages send to the Studio.
const STEPS = [
    { label: "Documents", href: "/documents" },
    { label: "Profile", href: "/profile" },
    { label: "Projects", href: "/projects" },
];

// Black bar on the onboarding pages: the wordmark and the three steps as pills
// (done / current / upcoming, design: DOCUMENTS.md → Header). The Projects step shows its steps on
// the page instead, so its bar only says "Setup · step 3 of 3" (STUDIO.md → Onboarding step 3).
const OnboardingHeader = () => {
    const pathname = usePathname();
    const current = STEPS.findIndex((step) => pathname.startsWith(step.href));
    if (current === STEPS.length - 1) {
        return (
            <header className={styles.header}>
                <Link href="/documents" className={styles.wordmark}>
                    OpenArt
                </Link>
                <span className={styles.setup}>Setup · step 3 of 3</span>
            </header>
        );
    }

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
                            <li key={step.label}>
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
