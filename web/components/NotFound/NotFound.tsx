import Link from "next/link";
import styles from "./NotFound.module.css";

type NotFoundProps = {
    title?: string;
    message?: string;
};

// "Not found", in the gallery's terms: an empty frame on the wall with its museum label.
// Used for unknown addresses (app/not-found.tsx) and calls that no longer exist.
const NotFound = ({
    title = "Nothing here",
    message = "This page doesn't exist, or it has moved. The calls are still where you left them.",
}: NotFoundProps) => (
    <main id="main" className={styles.main}>
        <div className={styles.text}>
            <p className={styles.code}>404</p>
            <h1 className={styles.title}>
                {title}
                <span className={styles.stop}>.</span>
            </h1>
            <p className={styles.message}>{message}</p>
            <Link href="/discover" className={styles.button}>
                Back to Discover →
            </Link>
        </div>

        {/* decoration: the frame and its label say the same thing as the heading */}
        <figure aria-hidden="true" className={styles.artwork}>
            <div className={styles.frame}>
                <div className={styles.canvas} />
            </div>
            <figcaption className={styles.label}>
                <span className={styles.labelTitle}>Untitled (404)</span>
                <span>2026 · A page, missing</span>
                <span className={styles.labelNote}>On loan to nowhere</span>
            </figcaption>
        </figure>
    </main>
);

export default NotFound;
