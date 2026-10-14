"use client";

import Link from "next/link";
import { useState } from "react";
import { countText, DOCUMENT_NAMES, textLimit } from "@/lib/apply";
import { thumbUrl } from "@/lib/images";
import type { ApplicationData, ApplicationItem } from "@/lib/types";
import { isManual, Mark, stateOf } from "./Checklist";
import styles from "./Apply.module.css";

type DraftColumnProps = {
    data: ApplicationData;
    text: ApplicationItem | null;      // the selected item to write, or
    gather: ApplicationItem | null;    // the selected item to gather
    draft: string;                     // what the box shows: the artist's unsaved edit, else the saved draft
    readOnly: boolean;                 // the call is closed
    cue: boolean;                      // the assistant just wrote a new version
    onDismissCue: () => void;
    onChange: (text: string) => void;
    onSave: (text: string) => Promise<string | null>;
    onReview: () => Promise<void>;
    onTick: (ticked: boolean) => void;
    onChooseImages: () => void;
};

// what each kind of item to gather needs from the artist, in a sentence
const helpFor = (item: ApplicationItem) => {
    const doc = DOCUMENT_NAMES[item.document ?? ""];
    if (item.state === "uploaded") return `Your ${doc} from your documents will be included in the package.`;
    if (item.document) return `Upload your ${doc} in your Studio: it will be included in the package.`;
    if (item.images_wanted)
        return "Choose images from your projects. They go into the package's folder in the order you tick them.";
    return "OpenArt can't collect this for you. Tick it once you have it, then add it to the folder yourself before submitting.";
};

// The centre column (design: APPLICATION.md → Draft). For a text: its draft, editable, counted against
// the call's limit, with "[placeholders]" the assistant left, and the review step. Human in the loop:
// "I have reviewed this" is the artist's own click on the text they see, and any later change sets it
// back to "Draft, not reviewed" (api/applications.py). For an item to gather: what it needs.
const DraftColumn = ({ data, text, gather, draft, readOnly, cue, onDismissCue, onChange, onSave, onReview, onTick,
                       onChooseImages }: DraftColumnProps) => {
    const [feedback, setFeedback] = useState("");
    const [busy, setBusy] = useState(false);
    const [copied, setCopied] = useState(false);

    if (gather) {
        const state = stateOf(gather);
        return (
            <section aria-labelledby="draft-heading" className={styles.draftColumn}>
                <div className={styles.draftHead}>
                    <span className={styles.eyebrowMuted}>To gather</span>
                    <h2 id="draft-heading" className={styles.draftTitle}>{gather.title}</h2>
                    <span className={styles.draftMeta}>
                        <span className={styles.rowState}><Mark mark={state.mark} />{state.label}</span>
                        {gather.limit && <span className={styles.muted}>{gather.limit}</span>}
                    </span>
                </div>
                <p className={styles.help}>{helpFor(gather)}</p>
                {gather.document && (
                    <div className={styles.fileRow}>
                        <span className={styles.fileName}>
                            {data.documents.find((d) => d.kind === gather.document)?.file_name ?? "Not uploaded"}
                        </span>
                        <Link href={`/studio?edit=${gather.document}`} className={styles.smallLink}>Upload or replace</Link>
                    </div>
                )}
                {gather.images_wanted && gather.state !== "uploaded" && (
                    <>
                        {gather.images.length > 0 && (
                            <ul className={styles.bigThumbs}>
                                {gather.images.map((image, n) => (
                                    <li key={image.id} className={styles.bigThumb}>
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img src={thumbUrl(image.id)} alt={`Image ${n + 1}`} loading="lazy" />
                                        <span className={styles.bigThumbNumber} aria-hidden="true">{String(n + 1).padStart(2, "0")}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                        {!readOnly && <button type="button" className={styles.darkButton} onClick={onChooseImages}>Choose images →</button>}
                    </>
                )}
                {isManual(gather) && (
                    <label className={styles.haveItBig}>
                        <input type="checkbox" checked={gather.state === "ticked"} disabled={readOnly}
                               onChange={(event) => onTick(event.target.checked)} />
                        <span>I have it, ready to attach</span>
                    </label>
                )}
            </section>
        );
    }

    if (!text) {
        return (
            <section className={styles.draftColumn}>
                <div className={styles.nothing}>
                    <h2 className={styles.draftTitle}>Nothing to draft for this call</h2>
                    <p className={styles.help}>The call only asks for files and images. Gather the items in the checklist, then download the package.</p>
                </div>
            </section>
        );
    }

    const state = stateOf(text);
    const limit = textLimit(text.limit);
    const count = countText(draft, limit?.unit ?? "words");
    const over = limit ? count - limit.max : 0;
    const changed = draft !== (text.draft ?? "");
    const holes = Array.from(new Set(draft.match(/\[[^\]\n]{2,80}\]/g) ?? []));
    const canReview = text.state !== "confirmed" && draft.trim() !== "";

    const save = async () => {
        setBusy(true);
        const problem = await onSave(draft);
        setBusy(false);
        setFeedback(problem ?? "Saved");
    };
    const review = async () => {
        setBusy(true);
        await onReview();
        setBusy(false);
        setFeedback("Reviewed by you");
    };
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(draft);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
        } catch {
            setFeedback("Couldn't copy: select the text and copy it yourself.");
        }
    };

    return (
        <section aria-labelledby="draft-heading" className={styles.draftColumn}>
            <div className={styles.draftHead}>
                <h2 id="draft-heading" className={styles.draftTitle}>{text.title}</h2>
                <span className={styles.draftMeta}>
                    <span className={styles.rowState}>
                        <Mark mark={state.mark} />
                        {text.state === "draft" ? "Draft, not reviewed yet" : state.label}
                    </span>
                    {text.limit && <span className={styles.muted}>{text.limit}</span>}
                </span>
            </div>
            {cue && (
                <div role="status" className={styles.cue}>
                    <span>New version from the assistant</span>
                    <button type="button" aria-label="Dismiss" onClick={onDismissCue}>×</button>
                </div>
            )}
            <label htmlFor="draft-text" className={styles.visuallyHidden}>{text.title}</label>
            <textarea
                id="draft-text"
                className={`${styles.draftArea} ${over > 0 ? styles.draftOver : ""}`}
                value={draft}
                readOnly={readOnly}
                placeholder="Write here, or ask the assistant for a first draft."
                aria-describedby="draft-count"
                onChange={(event) => {
                    onChange(event.target.value);
                    setFeedback("");
                }}
            />
            <div className={styles.countRow}>
                <span id="draft-count" aria-live="polite" className={`${styles.count} ${over > 0 ? styles.countOver : ""}`}>
                    {limit ? `${count} / ${limit.max} ${limit.unit}${over > 0 ? ` · ${over} over the limit` : ""}` : `${count} words`}
                </span>
                <span aria-live="polite" className={styles.feedback}>{feedback}</span>
            </div>
            {holes.length > 0 && (
                <div className={styles.holes}>
                    <span>Still to fill in:</span>
                    {holes.map((hole) => <span key={hole} className={styles.hole}>{hole}</span>)}
                </div>
            )}
            {!readOnly && (
                <div className={styles.draftActions}>
                    {canReview && (
                        <button type="button" className={styles.limeButton} onClick={review} disabled={busy}>I have reviewed this</button>
                    )}
                    <button type="button" className={styles.outlineButton} onClick={save} disabled={!changed || busy}>Save draft</button>
                    <button type="button" className={styles.outlineButton} onClick={copy} disabled={!draft.trim()}>
                        {copied ? "Copied" : "Copy text"}
                    </button>
                </div>
            )}
            <p className={styles.note}>Nothing is sent anywhere: when the drafts are ready, you copy them into the call&apos;s own form.</p>
        </section>
    );
};

export default DraftColumn;
