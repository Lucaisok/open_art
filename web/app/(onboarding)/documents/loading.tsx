import styles from "@/components/DocumentsBoard/DocumentsBoard.module.css";
import { CardBone, LoadingLabel } from "@/components/Skeleton/Skeleton";

// Shown while the server loads the artist's documents: the heading, and the three upload cards as placeholders
export default function DocumentsLoading() {
    return (
        <main id="main" className={styles.main}>
            <h1 className={styles.title}>
                Your documents<span className={styles.stop}>.</span>
            </h1>
            <LoadingLabel>Loading your documents…</LoadingLabel>
            <div className={styles.grid}>
                {[0, 1, 2].map((i) => (
                    <CardBone key={i} minHeight="460px" />
                ))}
            </div>
        </main>
    );
}
