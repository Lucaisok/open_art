import Link from "next/link";
import styles from "./ProfileEditor.module.css";

type CvBannerProps = {
    hasDocuments: boolean; // any document uploaded
    documents: string[]; // file names read for suggestions (not yet reviewed)
    found: number | null; // values read from them (null: everything already reviewed)
    filled: number; // empty fields we filled in
    differing: string[]; // labels of the saved fields where a document says something else
};

// "cv.pdf", "cv.pdf and statement.docx", "cv.pdf, statement.docx and portfolio.txt"
const listNames = (names: string[]) =>
    names.length <= 1 ? (names[0] ?? "") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;

// Under the heading: what we did with the artist's documents (design: OpenArt Profile prototype,
// a line with a left rule: lime when we filled fields in, ink otherwise). The documents were read
// by rules on our own server (src/rag/cv_rules.py); nothing is sent anywhere.
const CvBanner = ({ hasDocuments, documents, found, filled, differing }: CvBannerProps) => {
    let title: string;
    let text: string;
    let filledIn = false;
    let toDocuments = false;
    if (!hasDocuments && documents.length === 0 && found === null) {
        title = "No documents yet";
        text = "Add your CV and we'll fill in what it says, with the line each value came from. You can also fill the form in yourself.";
        toDocuments = true;
    } else if (found === 0) {
        title = "Nothing found in your documents";
        text = `We read ${listNames(documents)}, but it doesn't state any of these facts. Fill in whatever applies below.`;
    } else if (filled > 0) {
        title = `We filled in ${filled} ${filled === 1 ? "field" : "fields"} from ${listNames(documents)}`;
        text = "They're marked in lime with the line each value came from. Check them, then save. Nothing is saved until you do.";
        filledIn = true;
    } else if (differing.length > 0) {
        title = `We read ${listNames(documents)}`;
        text = "Nothing new to fill in, but some of it differs from what you saved.";
    } else {
        return null; // nothing new (or everything already reviewed)
    }

    return (
        <div role="status" className={`${styles.banner} ${filledIn ? styles.bannerLime : ""}`}>
            <p className={styles.bannerTitle}>{title}</p>
            <p className={styles.bannerText}>{text}</p>
            {differing.length > 0 && (
                <p className={styles.bannerConflicts}>
                    {differing.length} {differing.length === 1 ? "field where your documents say" : "fields where your documents say"}{" "}
                    something different from what&apos;s saved: {differing.join(", ")}. Choose which to keep below.
                </p>
            )}
            {toDocuments && (
                <Link href="/documents" className={styles.bannerLink}>
                    ← Go to Documents
                </Link>
            )}
        </div>
    );
};

export default CvBanner;
