import styles from "@/components/Discover/DiscoverBoard.module.css";
import { Bone, CardBone, LoadingLabel } from "@/components/Skeleton/Skeleton";

// Shown while the server runs the first search (the first "Matched to you" after an upload embeds
// the new document, ~1 s each, then cached): the page's own heading, placeholders for the rest.
export default function DiscoverLoading() {
    return (
        <main id="main" className={styles.main}>
            <div className={styles.titleRow}>
                <h1 className={styles.title}>
                    Discover calls<span className={styles.stop}>.</span>
                </h1>
                <Bone width="300px" height="58px" radius="14px" />
            </div>
            <div className={styles.searchRow}>
                <Bone height="56px" radius="14px" />
            </div>
            <section className={styles.results}>
                <div className={styles.resultsHead}>
                    <h2 className={styles.resultsTitle}>Results</h2>
                    <Bone width="180px" height="14px" />
                </div>
                <LoadingLabel>Searching calls…</LoadingLabel>
                <div className={styles.grid}>
                    {[0, 1, 2, 3, 4, 5].map((i) => (
                        <CardBone key={i} />
                    ))}
                </div>
            </section>
        </main>
    );
}
