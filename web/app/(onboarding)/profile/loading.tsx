import SetupSteps from "@/components/Onboarding/SetupSteps";
import onboarding from "@/components/Onboarding/Onboarding.module.css";
import styles from "@/components/ProfileEditor/ProfileEditor.module.css";
import { Bone, LoadingLabel } from "@/components/Skeleton/Skeleton";

// Shown while the server loads the profile, its options and the documents' suggestions: the steps,
// the heading, and the form's three sections (head rule, then field rows) as placeholders
export default function ProfileLoading() {
    return (
        <main id="main" className={onboarding.main}>
            <SetupSteps current={1} />
            <div className={onboarding.intro}>
                <h1 className={onboarding.title}>Your profile</h1>
                <LoadingLabel>Loading your profile…</LoadingLabel>
            </div>
            {[0, 1, 2].map((i) => (
                <div key={i} className={styles.section} aria-hidden="true">
                    <Bone height="24px" />
                    <div className={styles.fields}>
                        {[0, 1, 2, 3].map((j) => (
                            <div key={j} className={styles.field}>
                                <Bone width="160px" height="20px" />
                                <Bone height="40px" />
                            </div>
                        ))}
                    </div>
                </div>
            ))}
        </main>
    );
}
