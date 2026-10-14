import Link from "next/link";
import { DOCUMENT_NAMES, STATES } from "@/lib/apply";
import type { ApplicationData, ApplicationItem } from "@/lib/types";
import styles from "./Apply.module.css";

type ChecklistProps = {
    data: ApplicationData;
    selected: string | null;
    onSelect: (key: string) => void;
    onTick: (key: string, ticked: boolean) => void;
};

const StateLine = ({ item }: { item: ApplicationItem }) => (
    <span className={styles.state}>
        <span aria-hidden="true" className={`${styles.stateIcon} ${styles[item.state]}`}>
            {STATES[item.state].icon}
        </span>
        {STATES[item.state].label}
        {item.state === "uploaded" && item.document && `: your ${DOCUMENT_NAMES[item.document]}`}
    </span>
);

// The side column: what to write (each one selects what the chat and the draft are about), what to
// gather (✓ when the matching document is uploaded, else a tick the artist sets), and the documents.
const Checklist = ({ data, selected, onSelect, onTick }: ChecklistProps) => (
    <nav aria-label="What this application needs" className={styles.checklist}>
        <h2 className={styles.columnTitle}>To write · {data.to_draft.length}</h2>
        {data.to_draft.length === 0 ? (
            <p className={styles.hint}>This call asks for nothing written.</p>
        ) : (
            <ul className={styles.items}>
                {data.to_draft.map((item) => (
                    <li key={item.key}>
                        <button
                            type="button"
                            className={styles.item}
                            aria-current={item.key === selected ? "true" : undefined}
                            onClick={() => onSelect(item.key)}
                        >
                            <span className={styles.itemTitle}>{item.title}</span>
                            {item.limit && <span className={styles.itemLimit}>{item.limit}</span>}
                            <StateLine item={item} />
                        </button>
                    </li>
                ))}
            </ul>
        )}

        <h2 className={styles.columnTitle}>To gather · {data.to_gather.length}</h2>
        {data.to_gather.length === 0 ? (
            <p className={styles.hint}>Nothing to send besides the texts.</p>
        ) : (
            <ul className={styles.items}>
                {data.to_gather.map((item) => (
                    <li key={item.key} className={styles.gather}>
                        {item.state === "uploaded" ? (
                            <span className={styles.itemTitle}>{item.title}</span>
                        ) : (
                            // the artist's own "I have this": nothing is checked for them
                            <label className={styles.tick}>
                                <input
                                    type="checkbox"
                                    checked={item.state === "ticked"}
                                    onChange={(event) => onTick(item.key, event.target.checked)}
                                />
                                <span className={styles.itemTitle}>{item.title}</span>
                            </label>
                        )}
                        {item.limit && <span className={styles.itemLimit}>{item.limit}</span>}
                        <StateLine item={item} />
                    </li>
                ))}
            </ul>
        )}

        <h2 className={styles.columnTitle}>Your documents</h2>
        {data.documents.length === 0 ? (
            <p className={styles.hint}>None uploaded yet.</p>
        ) : (
            <ul className={styles.documents}>
                {data.documents.map((d) => (
                    <li key={d.kind}>
                        <span className={styles.documentKind}>{DOCUMENT_NAMES[d.kind] ?? d.kind}</span> {d.file_name}
                    </li>
                ))}
            </ul>
        )}
        <Link href="/documents" className={styles.textLink}>
            Upload or replace documents →
        </Link>
    </nav>
);

export default Checklist;
