import styles from "@/components/Discover/DiscoverBoard.module.css";

// Shown while the server runs the first search: the first "Matched to you" after an upload
// embeds the new document (~1 s each, then cached). The design's placeholder cards.
export default function DiscoverLoading() {
    return (
        <main id="main" className={styles.main}>
            <h1 className={styles.title}>
                Discover calls<span className={styles.stop}>.</span>
            </h1>
            <section aria-labelledby="results-heading" className={styles.results}>
                <div className={styles.resultsHead}>
                    <h2 id="results-heading" className={styles.resultsTitle}>
                        Results
                    </h2>
                    <p aria-live="polite" className={styles.count}>
                        Searching…
                    </p>
                </div>
                <div className={styles.grid} aria-hidden="true">
                    {[0, 1, 2].map((i) => (
                        <div key={i} className={styles.skeleton} />
                    ))}
                </div>
            </section>
        </main>
    );
}
