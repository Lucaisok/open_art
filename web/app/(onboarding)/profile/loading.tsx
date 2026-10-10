import styles from "@/components/ProfileEditor/ProfileEditor.module.css";
import { Bone, LoadingLabel } from "@/components/Skeleton/Skeleton";

// Shown while the server loads the profile, its options and the CV's suggestions: the heading,
// and the form's three groups (number and title on the left, fields on the right) as placeholders
export default function ProfileLoading() {
    return (
        <main id="main" className={styles.main}>
            <h1 className={styles.title}>
                Your profile<span className={styles.stop}>.</span>
            </h1>
            <LoadingLabel>Loading your profile…</LoadingLabel>
            <div className={styles.layout}>
                {[0, 1, 2].map((i) => (
                    <div key={i} className={styles.group} aria-hidden="true">
                        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                            <Bone width="40px" height="40px" />
                            <Bone width="70%" height="26px" />
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                            {[0, 1, 2].map((j) => (
                                <div key={j} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                    <Bone width="140px" height="14px" />
                                    <Bone height="48px" radius="12px" />
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </main>
    );
}
