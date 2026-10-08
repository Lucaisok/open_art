import type { Metadata } from "next";
import { redirect } from "next/navigation";
import DocumentSlot from "@/components/DocumentSlot/DocumentSlot";
import { getDocuments } from "@/lib/documents";
import { getCurrentUser } from "@/lib/session";
import type { DocumentKind } from "@/lib/types";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Your documents · OpenArt" };

// The three slots, in the order an artist usually has them ready
const SLOTS: { kind: DocumentKind; title: string; use: string }[] = [
    {
        kind: "cv",
        title: "CV",
        use: "Read for your education, exhibitions, awards and dates, to fill in your profile.",
    },
    {
        kind: "statement",
        title: "Artist statement",
        use: "Read to suggest what to search for, and quoted when drafting applications.",
    },
    {
        kind: "portfolio",
        title: "Portfolio",
        use: "Titles, captions and descriptions of your works. Only the text is read, not images.",
    },
];

// The first screen after sign-up: upload CV, statement and portfolio
export default async function DocumentsPage() {
    const user = await getCurrentUser();
    if (!user) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const documents = await getDocuments();

    return (
        <main id="main" className={styles.main}>
            <h1 className={styles.title}>Your documents.</h1>
            <p className={styles.lead}>
                OpenArt reads them to fill in your profile and to find calls that fit your practice. Only you can
                see them. PDF, DOCX, TXT or MD, up to 10 MB each.
            </p>
            <ul className={styles.slots}>
                {SLOTS.map((slot) => (
                    <li key={slot.kind}>
                        <DocumentSlot
                            kind={slot.kind}
                            title={slot.title}
                            use={slot.use}
                            document={documents.find((d) => d.kind === slot.kind) ?? null}
                        />
                    </li>
                ))}
            </ul>
        </main>
    );
}
