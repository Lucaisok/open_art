import { DOCUMENT_NAMES } from "@/lib/apply";
import { thumbUrl } from "@/lib/images";
import type { ApplicationData, ApplicationItem } from "@/lib/types";
import styles from "./Apply.module.css";

// how far an item is: an empty square, half-filled, or lime (never colour alone: the words follow)
export const stateOf = (item: ApplicationItem): { label: string; mark: "empty" | "half" | "done" } => {
    switch (item.state) {
        case "confirmed":
            return { label: "Reviewed by you", mark: "done" };
        case "draft":
            return { label: "Draft, not reviewed", mark: "half" };
        case "uploaded":
            return { label: `Uploaded (your ${DOCUMENT_NAMES[item.document ?? ""] ?? "document"})`, mark: "done" };
        case "chosen":
            return { label: `Images chosen · ${item.images.length}`, mark: "done" };
        case "ticked":
            return { label: "You have it", mark: "done" };
        case "missing":
            return { label: "To get", mark: "empty" };
        default:
            return { label: "Not started", mark: "empty" };
    }
};

export const Mark = ({ mark }: { mark: "empty" | "half" | "done" }) => (
    <span aria-hidden="true" className={`${styles.mark} ${styles[`mark_${mark}`]}`} />
);

// an item to gather with nothing to upload or choose: the artist's own "I have it"
export const isManual = (item: ApplicationItem) => !item.images_wanted && !item.document;

type ChecklistProps = {
    data: ApplicationData;
    selected: string | null;
    readOnly: boolean;
    onSelect: (key: string) => void;
    onTick: (key: string, ticked: boolean) => void;
    onChooseImages: (key: string) => void;
};

// The left column (design: APPLICATION.md → Checklist): the texts to write, then the items to gather,
// each with its state. Selecting one shows it in the centre column.
const Checklist = ({ data, selected, readOnly, onSelect, onTick, onChooseImages }: ChecklistProps) => (
    <nav aria-label="What this application needs" className={styles.checklist}>
        <h2 className={styles.columnHead}>To write · {data.to_draft.length}</h2>
        {data.to_draft.length === 0 && <p className={styles.columnHint}>This call asks for nothing written.</p>}
        {data.to_draft.map((item) => {
            const state = stateOf(item);
            return (
                <button key={item.key} type="button" className={styles.row} aria-current={item.key === selected ? "true" : undefined}
                        onClick={() => onSelect(item.key)}>
                    <span className={styles.rowTitle}>{item.title}</span>
                    {item.limit && <span className={styles.rowMeta}>{item.limit}</span>}
                    <span className={styles.rowState}><Mark mark={state.mark} />{state.label}</span>
                </button>
            );
        })}

        <h2 className={`${styles.columnHead} ${styles.columnHeadNext}`}>To gather · {data.to_gather.length}</h2>
        {data.to_gather.length === 0 && <p className={styles.columnHint}>Nothing to send besides the texts.</p>}
        {data.to_gather.map((item) => {
            const state = stateOf(item);
            return (
                <div key={item.key} className={styles.gatherRow} aria-current={item.key === selected ? "true" : undefined}>
                    <button type="button" className={styles.gatherPick} onClick={() => onSelect(item.key)}>
                        <span className={styles.rowTitle}>{item.title}</span>
                        {item.limit && <span className={styles.rowMeta}>{item.limit}</span>}
                    </button>
                    <span className={styles.rowState}><Mark mark={state.mark} />{state.label}</span>
                    {item.images_wanted && item.state !== "uploaded" && (
                        <>
                            {item.images.length > 0 && (
                                <span className={styles.miniThumbs}>
                                    {item.images.slice(0, 8).map((image) => (
                                        // eslint-disable-next-line @next/next/no-img-element
                                        <img key={image.id} src={thumbUrl(image.id)} alt="" loading="lazy" />
                                    ))}
                                </span>
                            )}
                            {!readOnly && (
                                <button type="button" className={styles.textButton} onClick={() => onChooseImages(item.key)}>
                                    Choose images from your projects
                                </button>
                            )}
                        </>
                    )}
                    {isManual(item) && (
                        <label className={styles.haveIt}>
                            <input type="checkbox" checked={item.state === "ticked"} disabled={readOnly}
                                   onChange={(event) => onTick(item.key, event.target.checked)} />
                            <span>I have it</span>
                        </label>
                    )}
                </div>
            );
        })}
    </nav>
);

export default Checklist;
