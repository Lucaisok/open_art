"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./OnboardingHeader.module.css";

// The onboarding pages, in order (design: STUDIO.md → App structure). The last one ends in
// "Continue to Discover", after which these pages send to the Studio.
const STEPS = ["/documents", "/profile", "/projects"];

// Black bar on the onboarding pages: the wordmark and "Setup · step N of 3" (design: OpenArt
// Documents / Profile prototypes). The steps themselves are on the page (components/Onboarding/SetupSteps).
const OnboardingHeader = () => {
    const pathname = usePathname();
    const current = Math.max(0, STEPS.findIndex((href) => pathname.startsWith(href)));
    return (
        <header className={styles.header}>
            <Link href="/documents" className={styles.wordmark}>
                OpenArt
            </Link>
            <span className={styles.setup}>Setup · step {current + 1} of 3</span>
        </header>
    );
};

export default OnboardingHeader;
