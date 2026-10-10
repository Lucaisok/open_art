import styles from "@/components/Opportunity/OpportunityView.module.css";
import { Bone, LoadingLabel } from "@/components/Skeleton/Skeleton";

// Shown while the server loads the call and works out its verdict: the page's two columns,
// facts on the left, "Can you apply?" on the right, as placeholders
export default function OpportunityLoading() {
    return (
        <main id="main" className={styles.main}>
            <LoadingLabel>Loading the call…</LoadingLabel>
            <Bone width="150px" height="20px" />
            <div style={{ display: "flex", gap: 6, marginTop: 24 }}>
                <Bone width="90px" height="24px" radius="999px" />
                <Bone width="70px" height="24px" radius="999px" />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16, maxWidth: 760 }}>
                <Bone width="90%" height="clamp(36px, 5.6vw, 64px)" />
                <Bone width="55%" height="clamp(36px, 5.6vw, 64px)" />
            </div>
            <Bone width="280px" height="18px" className={styles.byline} />

            <div className={styles.columns}>
                <div className={styles.facts}>
                    <dl className={styles.factList}>
                        {[0, 1, 2, 3, 4].map((i) => (
                            <div key={i} className={styles.fact}>
                                <Bone width="120px" height="16px" />
                                <Bone width="40%" height="16px" />
                            </div>
                        ))}
                    </dl>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 32 }}>
                        <Bone width="160px" height="22px" />
                        <Bone height="14px" />
                        <Bone height="14px" />
                        <Bone width="75%" height="14px" />
                    </div>
                </div>

                <section className={styles.apply}>
                    <h2 className={styles.applyTitle}>Can you apply?</h2>
                    <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 20 }}>
                        <Bone width="200px" height="40px" radius="999px" />
                        <Bone width="80%" height="14px" />
                        {[0, 1, 2].map((i) => (
                            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 14 }}>
                                <Bone height="16px" />
                                <Bone width="85%" height="16px" />
                                <Bone width="45%" height="12px" />
                            </div>
                        ))}
                    </div>
                </section>
            </div>
        </main>
    );
}
