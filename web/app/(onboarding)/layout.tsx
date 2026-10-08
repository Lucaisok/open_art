import OnboardingHeader from "@/components/OnboardingHeader/OnboardingHeader";
import styles from "./layout.module.css";

// Documents and Profile: the onboarding steps after sign-up. The step-pill header on top;
// each page brings its own footer bar (Back, progress, Continue / Save).
export default function OnboardingLayout({ children }: Readonly<{ children: React.ReactNode }>) {
    return (
        <div className={styles.shell}>
            <OnboardingHeader />
            {children}
        </div>
    );
}
