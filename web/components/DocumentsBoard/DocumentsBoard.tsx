"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import type { DocumentInfo, DocumentKind } from "@/lib/types";
import UploadCard, { type SlotInfo } from "./UploadCard";
import styles from "./DocumentsBoard.module.css";

// The three slots (design: design_handoff_openart 2, DOCUMENTS.md → Slots). One file each:
// the API keeps one document per slot, PDF / DOCX / TXT / MD up to 10 MB (src/rag/documents.py).
const SLOTS: SlotInfo[] = [
    {
        kind: "cv",
        number: "01",
        title: "CV",
        description: "Exhibitions, education, awards and dates. Used for eligibility checks like years of practice.",
        readResult: (n) => `${n} ${n === 1 ? "passage" : "passages"} read`,
    },
    {
        kind: "statement",
        number: "02",
        title: "Artist statement",
        description: "How you describe your practice. Used for matching and quoted back to you in drafts.",
        readResult: (n) => `${n} ${n === 1 ? "passage" : "passages"} indexed`,
    },
    {
        kind: "portfolio",
        number: "03",
        title: "Portfolio",
        description: "Selected works with their titles and captions, as one file. Only the text is read, not images.",
        readResult: () => "Ready",
    },
];

type DocumentsBoardProps = {
    initialDocuments: DocumentInfo[];
    onboarding: boolean;   // the profile was never saved: the footer bar leads on to the profile
};

// The Documents page body: title, the three upload cards and, during the onboarding only, the
// footer bar ("N of 3 added", Skip, Continue). Each card uploads on its own; the board only counts.
// Outside the onboarding there is no bar: uploads save themselves and the header leads everywhere.
const DocumentsBoard = ({ initialDocuments, onboarding }: DocumentsBoardProps) => {
    // which slots hold a document, and which are uploading: for the footer
    const [added, setAdded] = useState<Record<DocumentKind, boolean>>({
        cv: initialDocuments.some((d) => d.kind === "cv"),
        statement: initialDocuments.some((d) => d.kind === "statement"),
        portfolio: initialDocuments.some((d) => d.kind === "portfolio"),
    });
    const [busy, setBusy] = useState<Record<DocumentKind, boolean>>({ cv: false, statement: false, portfolio: false });

    // stable callbacks (the cards call them from effects); unchanged values keep the same state object
    const onAddedChange = useCallback(
        (kind: DocumentKind, value: boolean) =>
            setAdded((prev) => (prev[kind] === value ? prev : { ...prev, [kind]: value })),
        [],
    );
    const onBusyChange = useCallback(
        (kind: DocumentKind, value: boolean) =>
            setBusy((prev) => (prev[kind] === value ? prev : { ...prev, [kind]: value })),
        [],
    );

    const addedCount = Object.values(added).filter(Boolean).length;
    const anyBusy = Object.values(busy).some(Boolean);
    const canContinue = addedCount > 0 && !anyBusy;

    return (
        <>
            <main id="main" className={styles.main}>
                <h1 className={styles.title}>
                    Your documents<span className={styles.stop}>.</span>
                </h1>
                <p className={styles.intro}>
                    We read these to match you with calls, check eligibility and pull the right passages into your
                    drafts. You can replace them any time.
                </p>
                <ul className={styles.grid}>
                    {SLOTS.map((slot) => (
                        <li key={slot.kind} className={styles.gridItem}>
                            <UploadCard
                                slot={slot}
                                initialDocument={initialDocuments.find((d) => d.kind === slot.kind) ?? null}
                                onAddedChange={onAddedChange}
                                onBusyChange={onBusyChange}
                            />
                        </li>
                    ))}
                </ul>
            </main>

            {onboarding && (
                <footer className={styles.footer}>
                    <div className={styles.footerLeft}>
                        <p className={styles.progress} aria-live="polite">
                            {addedCount} of 3 added
                        </p>
                    </div>
                    <div className={styles.footerRight}>
                        <Link href="/profile" className={styles.skip}>
                            Skip for now
                        </Link>
                        {canContinue ? (
                            <Link href="/profile" className={styles.continue}>
                                <span>Continue</span>
                                <span className={styles.arrow} aria-hidden="true">
                                    →
                                </span>
                            </Link>
                        ) : (
                            // disabled until one document is added and nothing is uploading
                            <button type="button" className={styles.continue} disabled>
                                <span>Continue</span>
                                <span className={styles.arrow} aria-hidden="true">
                                    →
                                </span>
                            </button>
                        )}
                    </div>
                </footer>
            )}
        </>
    );
};

export default DocumentsBoard;
