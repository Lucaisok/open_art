import Header from "@/components/Header/Header";
import OnboardingHeader from "@/components/OnboardingHeader/OnboardingHeader";
import { apiGet } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { ProfileData } from "@/lib/types";
import styles from "./layout.module.css";

// Documents and Profile. During the onboarding (no profile saved yet): the step-pill header.
// Afterwards they are ordinary pages of the site, reached from the main header, so they get it too.
// Each page brings its own footer bar (Back, progress, Continue / Save).
export default async function OnboardingLayout({ children }: Readonly<{ children: React.ReactNode }>) {
    const onboarded =
        (await getCurrentUser()) !== null && (await apiGet<ProfileData>("/api/profile")).updated_at !== null;
    return (
        <div className={styles.shell}>
            {onboarded ? <Header /> : <OnboardingHeader />}
            {children}
        </div>
    );
}
