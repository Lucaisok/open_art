import Link from "next/link";
import styles from "./ProfileEditor.module.css";

type CvBannerProps = {
    cvName: string | null; // the uploaded CV, if any
    documents: string[]; // file names read for suggestions (not yet reviewed)
    found: number | null; // values read from them (null: everything already reviewed)
    filled: number; // empty fields we filled in
    differing: number; // saved fields where a document says something else
};

// "cv.pdf", "cv.pdf and statement.docx", "cv.pdf, statement.docx and portfolio.txt"
const listNames = (names: string[]) =>
    names.length <= 1 ? (names[0] ?? "") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;

// Above the form: what we did with the artist's documents. They were read by rules on our own
// server (src/rag/cv_rules.py); nothing is sent anywhere.
const CvBanner = ({ cvName, documents, found, filled, differing }: CvBannerProps) => {
    if (!cvName && documents.length === 0 && found === null) {
        return (
            <aside className={styles.banner} aria-labelledby="cv-banner-title">
                <p className={styles.bannerEyebrow}>From your documents</p>
                <h2 id="cv-banner-title" className={styles.bannerTitle}>
                    Let us fill this in.
                </h2>
                <p className={styles.bannerText}>
                    Add your CV, statement or portfolio and we&apos;ll read your details from them: birth date,
                    nationality, education, disciplines and more. They&apos;re read on OpenArt&apos;s own server and
                    never sent anywhere else.
                </p>
                <Link href="/documents" className={styles.bannerLink}>
                    Add your documents →
                </Link>
            </aside>
        );
    }
    if (found === 0) {
        return (
            <aside className={styles.banner} aria-labelledby="cv-banner-title">
                <p className={styles.bannerEyebrow}>From your documents</p>
                <h2 id="cv-banner-title" className={styles.bannerTitle}>
                    We couldn&apos;t find these details in {listNames(documents)}.
                </h2>
                <p className={styles.bannerText}>
                    We look for lines like &ldquo;Born 12 March 1994&rdquo;, &ldquo;Citizenship: …&rdquo;,
                    &ldquo;Based in …&rdquo;, degrees under Education, and what your statement says you make. Fill
                    the fields in below; it takes a minute.
                </p>
            </aside>
        );
    }
    if (filled === 0 && differing === 0) {
        return null; // nothing new (or everything already reviewed)
    }
    return (
        <aside className={styles.banner} aria-labelledby="cv-banner-title">
            <p className={styles.bannerEyebrow}>From your documents</p>
            <h2 id="cv-banner-title" className={styles.bannerTitle}>
                {filled > 0
                    ? `We filled in ${filled} ${filled === 1 ? "field" : "fields"} from ${listNames(documents)}.`
                    : `${listNames(documents)} differ from your profile.`}
            </h2>
            <p className={styles.bannerText}>
                {filled > 0 && "Each is marked with the document it comes from, and the line is one click away. "}
                {differing > 0 &&
                    `Where a document says something different from what you saved (${differing} ${
                        differing === 1 ? "field" : "fields"
                    }), we kept yours and show what it says. `}
                Change anything that&apos;s wrong, then save.
            </p>
        </aside>
    );
};

export default CvBanner;
