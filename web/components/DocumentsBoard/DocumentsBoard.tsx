"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import type { DocumentInfo, DocumentKind } from "@/lib/types";
import SetupSteps from "@/components/Onboarding/SetupSteps";
import onboarding from "@/components/Onboarding/Onboarding.module.css";
import UploadCard, { type SlotInfo } from "./UploadCard";
import styles from "./DocumentsBoard.module.css";

// The three slots (design: design_handoff_openart, DOCUMENTS.md → Slots). One file each:
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

// Onboarding step 1 (design: OpenArt Documents prototype): the setup steps, the title, the three
// upload slots and the fixed bar ("N of 3 added", Skip, Continue). Each slot uploads on its own;
// the board only counts. After the onboarding, documents are managed in the Studio.
const DocumentsBoard = ({ initialDocuments }: { initialDocuments: DocumentInfo[] }) => {
    // which slots hold a document, and which are uploading: for the bar
    const [added, setAdded] = useState<Record<DocumentKind, boolean>>({
        cv: initialDocuments.some((d) => d.kind === "cv"),
        statement: initialDocuments.some((d) => d.kind === "statement"),
        portfolio: initialDocuments.some((d) => d.kind === "portfolio"),
    });
    const [busy, setBusy] = useState<Record<DocumentKind, boolean>>({ cv: false, statement: false, portfolio: false });

    // stable callbacks (the slots call them from effects); unchanged values keep the same state object
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
        <main id="main" className={onboarding.main}>
            <SetupSteps current={0} />
            <div className={onboarding.intro}>
                <h1 className={onboarding.title}>Your documents</h1>
                <p className={onboarding.lead}>
                    We read these to match you with calls, check eligibility and pull the right passages into your
                    drafts. You can replace them any time.
                </p>
            </div>

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

            <div className={onboarding.bar}>
                <div className={onboarding.barInner}>
                    {/* the first step: nothing to go back to (the login sends a logged-in artist here) */}
                    <span className={onboarding.status} aria-live="polite">
                        {addedCount} of 3 added
                    </span>
                    <span className={styles.barRight}>
                        <Link href="/profile" className={styles.skip}>
                            Skip for now
                        </Link>
                        {canContinue ? (
                            <Link href="/profile" className={`${styles.continue} ${onboarding.next}`}>
                                Continue →
                            </Link>
                        ) : (
                            // disabled until one document is added and nothing is uploading
                            <button type="button" className={`${styles.continue} ${onboarding.next}`} disabled>
                                Continue →
                            </button>
                        )}
                    </span>
                </div>
            </div>
        </main>
    );
};

export default DocumentsBoard;
