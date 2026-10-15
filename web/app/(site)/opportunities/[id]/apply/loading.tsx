import styles from "@/components/Apply/Apply.module.css";
import { Bone, LoadingLabel } from "@/components/Skeleton/Skeleton";

// Shown while the server loads the artist's application. Without it, Next.js falls back to the
// call page's loading.tsx (one segment up), and its "Can you apply?" placeholder flashes on the way
// in. Shaped like the application page: header, fact strip, then checklist · draft · assistant.
export default function ApplyLoading() {
    return (
        <main id="main" className={styles.main}>
            <LoadingLabel>Loading your application…</LoadingLabel>
            <section className={styles.header}>
                <div className={styles.topBar}>
                    <Bone width="130px" height="16px" />
                    <div style={{ display: "flex", gap: 10 }}>
                        <Bone width="90px" height="48px" radius="2px" />
                        <Bone width="200px" height="48px" radius="2px" />
                    </div>
                </div>
                <div className={styles.titleText}>
                    <span className={styles.eyebrow}>Draft an application</span>
                    <Bone width="70%" height="clamp(30px, 4vw, 48px)" />
                    <Bone width="260px" height="18px" />
                </div>
                <div className={styles.factStrip}>
                    {[0, 1, 2, 3].map((i) => (
                        <div key={i} className={styles.fact}>
                            <Bone width="90px" height="12px" />
                            <Bone width="60%" height="18px" />
                        </div>
                    ))}
                </div>
            </section>

            {/* on narrow screens only the first column shows, as on the real page's "Checklist" tab */}
            <div className={styles.workspace} data-view="checklist">
                <div className={styles.columnChecklist} style={{ gap: 14 }}>
                    {[0, 1, 2, 3, 4].map((i) => (
                        <Bone key={i} height="44px" radius="2px" />
                    ))}
                </div>
                <div className={styles.columnDraft} style={{ gap: 12 }}>
                    <Bone width="50%" height="22px" />
                    <Bone height="320px" radius="2px" />
                </div>
                <div className={styles.columnAssistant} style={{ gap: 12 }}>
                    <Bone width="40%" height="22px" />
                    <Bone height="320px" radius="2px" />
                </div>
            </div>
        </main>
    );
}
