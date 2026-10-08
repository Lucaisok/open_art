import Link from "next/link";
import styles from "./ProfileEditor.module.css";

type CvBannerProps = {
    cvName: string | null; // the uploaded CV, if any
    found: number | null; // values read from it and not yet reviewed (null: already reviewed)
    filled: number; // empty fields we filled in from it
    differing: number; // saved fields where the CV says something else
};

// Above the form: what we did with the CV. The CV was read when it was uploaded, by rules on
// our own server (src/rag/cv_rules.py); nothing is sent anywhere.
const CvBanner = ({ cvName, found, filled, differing }: CvBannerProps) => {
    if (!cvName) {
        return (
            <aside className={styles.banner} aria-labelledby="cv-banner-title">
                <p className={styles.bannerEyebrow}>From your CV</p>
                <h2 id="cv-banner-title" className={styles.bannerTitle}>
                    Let us fill this in.
                </h2>
                <p className={styles.bannerText}>
                    Add your CV and we&apos;ll read your details from it: birth date, nationality, education and
                    more. It&apos;s read on OpenArt&apos;s own server and never sent anywhere else.
                </p>
                <Link href="/documents" className={styles.bannerLink}>
                    Add your CV →
                </Link>
            </aside>
        );
    }
    if (found === 0) {
        return (
            <aside className={styles.banner} aria-labelledby="cv-banner-title">
                <p className={styles.bannerEyebrow}>From your CV</p>
                <h2 id="cv-banner-title" className={styles.bannerTitle}>
                    We couldn&apos;t find these details in {cvName}.
                </h2>
                <p className={styles.bannerText}>
                    We look for lines like &ldquo;Born 12 March 1994&rdquo;, &ldquo;Citizenship: …&rdquo;,
                    &ldquo;Based in …&rdquo; and degrees under Education. Fill the fields in below; it takes a
                    minute.
                </p>
            </aside>
        );
    }
    if (filled === 0 && differing === 0) {
        return null; // nothing new from this CV (or already reviewed)
    }
    return (
        <aside className={styles.banner} aria-labelledby="cv-banner-title">
            <p className={styles.bannerEyebrow}>From your CV</p>
            <h2 id="cv-banner-title" className={styles.bannerTitle}>
                {filled > 0
                    ? `We filled in ${filled} ${filled === 1 ? "field" : "fields"} from ${cvName}.`
                    : `${cvName} differs from your profile.`}
            </h2>
            <p className={styles.bannerText}>
                {filled > 0 && "They're marked “From your CV”, with the line each comes from one click away. "}
                {differing > 0 &&
                    `Where your CV says something different from what you saved (${differing} ${
                        differing === 1 ? "field" : "fields"
                    }), we kept yours and show what the CV says. `}
                Change anything that&apos;s wrong, then save.
            </p>
        </aside>
    );
};

export default CvBanner;
