import SetupSteps from "@/components/Onboarding/SetupSteps";
import onboarding from "@/components/Onboarding/Onboarding.module.css";
import styles from "@/components/DocumentsBoard/DocumentsBoard.module.css";
import { Bone, LoadingLabel } from "@/components/Skeleton/Skeleton";

// Shown while the server loads the artist's documents: the steps, the heading, and the three
// upload slots as placeholders
export default function DocumentsLoading() {
    return (
        <main id="main" className={onboarding.main}>
            <SetupSteps current={0} />
            <div className={onboarding.intro}>
                <h1 className={onboarding.title}>Your documents</h1>
                <LoadingLabel>Loading your documents…</LoadingLabel>
            </div>
            <div className={styles.grid} aria-hidden="true">
                {[0, 1, 2].map((i) => (
                    <div key={i} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        <Bone height="24px" />
                        <Bone width="60%" height="28px" />
                        <Bone height="44px" />
                        <Bone height="120px" radius="12px" />
                    </div>
                ))}
            </div>
        </main>
    );
}
