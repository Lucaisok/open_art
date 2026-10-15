"use client";

import { useState } from "react";
import styles from "./Apply.module.css";

type TitleFormProps = {
    initial?: string;
    submitLabel: string;                                  // "Add" or "Rename"
    onSubmit: (title: string) => Promise<string | null>;  // null = done, else the problem to show
    onCancel: () => void;
};

// The title of a text the artist adds themselves ("Cover letter"), or its new title when renaming
const TitleForm = ({ initial = "", submitLabel, onSubmit, onCancel }: TitleFormProps) => {
    const [title, setTitle] = useState(initial);
    const [busy, setBusy] = useState(false);
    const [problem, setProblem] = useState("");

    return (
        <form
            className={styles.titleForm}
            onSubmit={async (event) => {
                event.preventDefault();
                setBusy(true);
                const error = await onSubmit(title.trim());
                setBusy(false);
                setProblem(error ?? "");
            }}
        >
            <label htmlFor="text-title" className={styles.titleFormLabel}>Title of the text</label>
            <input id="text-title" className={styles.titleInput} value={title} maxLength={200} autoFocus required
                   placeholder="e.g. Cover letter" onChange={(event) => setTitle(event.target.value)}
                   onKeyDown={(event) => event.key === "Escape" && onCancel()} />
            {problem && <p role="alert" className={styles.error}>{problem}</p>}
            <div className={styles.titleFormButtons}>
                <button type="submit" className={styles.darkButton} disabled={busy || !title.trim()}>{submitLabel}</button>
                <button type="button" className={styles.outlineButton} onClick={onCancel}>Cancel</button>
            </div>
        </form>
    );
};

export default TitleForm;
