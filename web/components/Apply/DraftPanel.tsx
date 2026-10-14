"use client";

import { useState } from "react";
import { STATES, countText, textLimit } from "@/lib/apply";
import type { ApplicationItem } from "@/lib/types";
import styles from "./Apply.module.css";

type DraftPanelProps = {
    item: ApplicationItem;
    text: string;                         // what the box shows: the artist's unsaved edit, else the saved draft
    onChange: (text: string) => void;
    onSave: (text: string) => Promise<string | null>;   // null = saved, else the error
    onConfirm: () => Promise<string | null>;            // "I have reviewed this"
};

// The right column: the draft of the selected item, editable, counted against the call's limit.
// The text lives in ApplyWorkspace, so the agent revises what the artist sees, unsaved edits included.
// Human in the loop: "I have reviewed this" is the artist's own click, only on the saved text they see,
// and only a reviewed draft can be copied (the export route checks the same on the server).
// Rendered with key={item.key}, so switching item clears the messages.
const DraftPanel = ({ item, text, onChange, onSave, onConfirm }: DraftPanelProps) => {
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState("");
    const limit = textLimit(item.limit);
    const count = limit ? countText(text, limit.unit) : null;
    const over = limit !== null && count !== null && count > limit.max;
    const changed = text !== (item.draft ?? "");
    // the agent marks what it couldn't find: "[title of the planned work]"
    const placeholders = text.match(/\[[^\]\n]{2,80}\]/g) ?? [];

    const save = async () => {
        setSaving(true);
        const error = await onSave(text);
        setSaving(false);
        setMessage(error ?? "Saved.");
    };

    const confirm = async () => {
        setSaving(true);
        const error = await onConfirm();
        setSaving(false);
        setMessage(error ?? "Marked as reviewed.");
    };

    const copy = async () => {
        try {
            await navigator.clipboard.writeText(text);
            setMessage("Copied: paste it into the call's form.");
        } catch {
            setMessage("Couldn't copy: select the text and copy it yourself.");
        }
    };

    return (
        <section aria-labelledby="draft-heading" className={styles.draftPanel}>
            <h2 id="draft-heading" className={styles.columnTitle}>
                Draft
            </h2>
            <p className={styles.state}>
                <span aria-hidden="true" className={`${styles.stateIcon} ${styles[item.state]}`}>
                    {STATES[item.state].icon}
                </span>
                {STATES[item.state].label}
            </p>
            <label htmlFor="draft-text" className={styles.visuallyHidden}>
                Draft of: {item.title}
            </label>
            <textarea
                id="draft-text"
                className={styles.draftInput}
                value={text}
                onChange={(event) => {
                    onChange(event.target.value);
                    setMessage("");
                }}
                aria-describedby="draft-count"
            />
            <p id="draft-count" className={`${styles.count} ${over ? styles.countOver : ""}`}>
                {limit && count !== null
                    ? `${count} / ${limit.max} ${limit.unit}${over ? ": over the limit" : ""}`
                    : `${countText(text, "words")} words`}
            </p>
            {placeholders.length > 0 && (
                <p className={styles.placeholders}>
                    Still to fill in: {placeholders.join(", ")}
                </p>
            )}
            <div className={styles.draftActions}>
                <button type="button" className={styles.primary} onClick={save} disabled={!changed || saving}>
                    {saving ? "Saving…" : "Save draft"}
                </button>
                {item.state === "confirmed" && !changed ? (
                    <button type="button" className={styles.secondary} onClick={copy}>
                        Copy text
                    </button>
                ) : (
                    // only the saved text can be confirmed: what was reviewed is what is stored
                    <button type="button" className={styles.secondary} onClick={confirm}
                            disabled={changed || saving || item.state !== "draft"}>
                        I have reviewed this
                    </button>
                )}
                <p aria-live="polite" className={styles.saveMessage}>
                    {changed && !message ? "Unsaved changes" : message}
                </p>
            </div>
            <p className={styles.note}>
                Nothing is sent anywhere: when the drafts are ready, you copy them into the call&apos;s own form.
            </p>
        </section>
    );
};

export default DraftPanel;
