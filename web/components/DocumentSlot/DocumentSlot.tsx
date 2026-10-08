"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { sendFile, sendJson } from "@/lib/api";
import type { DocumentInfo, DocumentKind } from "@/lib/types";
import styles from "./DocumentSlot.module.css";

type DocumentSlotProps = {
    kind: DocumentKind;
    title: string;
    use: string; // what OpenArt does with this document
    document: DocumentInfo | null;
};

// Same limits as the API (src/rag/documents.py), checked here first so a wrong file
// is refused at once instead of after a 10 MB upload
const EXTENSIONS = [".pdf", ".docx", ".txt", ".md"];
const MAX_BYTES = 10 * 1024 * 1024;

const formatSize = (bytes: number) =>
    bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

// One of the three document cards: shows the uploaded file, or lets the artist upload one.
// A file is uploaded as soon as it is chosen (or dropped on the card); after an upload or a
// removal the page is re-rendered with the server's fresh list.
const DocumentSlot = ({ kind, title, use, document }: DocumentSlotProps) => {
    const router = useRouter();
    const inputRef = useRef<HTMLInputElement>(null);
    const dialogRef = useRef<HTMLDialogElement>(null);
    const [busy, setBusy] = useState<string | null>(null); // "Reading cv.pdf…" while a request runs
    const [error, setError] = useState<string | null>(null);
    const [dragging, setDragging] = useState(false);
    const inputId = `upload-${kind}`;

    const upload = async (file: File) => {
        setError(null);
        const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
        if (!EXTENSIONS.includes(extension)) {
            setError("Upload a PDF, DOCX, TXT or MD file.");
            return;
        }
        if (file.size > MAX_BYTES) {
            setError("The file is larger than 10 MB.");
            return;
        }
        setBusy(`Reading ${file.name}…`);
        const result = await sendFile(`/api/documents/${kind}`, file);
        setBusy(null);
        if (inputRef.current) {
            inputRef.current.value = ""; // so choosing the same file again uploads it again
        }
        if (!result.ok) {
            setError(result.error);
            return;
        }
        router.refresh();
    };

    const onChoose = (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file) {
            upload(file);
        }
    };

    // drag and drop is a shortcut only: the "Choose file" button does the same with the keyboard
    const onDrop = (event: DragEvent<HTMLElement>) => {
        event.preventDefault();
        setDragging(false);
        const file = event.dataTransfer.files[0];
        if (file && !busy) {
            upload(file);
        }
    };

    const remove = async () => {
        dialogRef.current?.close();
        setError(null);
        setBusy("Removing…");
        const result = await sendJson("DELETE", `/api/documents/${kind}`);
        setBusy(null);
        if (!result.ok) {
            setError(result.error);
            return;
        }
        router.refresh();
    };

    return (
        <section
            aria-labelledby={`${inputId}-title`}
            className={`${styles.card} ${dragging ? styles.dragging : ""}`}
            onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
        >
            <div className={styles.top}>
                <h2 id={`${inputId}-title`} className={styles.title}>
                    {title}
                </h2>
                <span className={document ? styles.badgeReady : styles.badgeEmpty}>
                    {document ? "Uploaded" : "Missing"}
                </span>
            </div>
            <p className={styles.use}>{use}</p>

            {document && (
                <p className={styles.file}>
                    <span className={styles.fileName}>{document.file_name}</span>
                    <span className={styles.fileMeta}>
                        {document.chunk_count} {document.chunk_count === 1 ? "passage" : "passages"} ·{" "}
                        {formatSize(document.size_bytes)} · {formatDate(document.uploaded_at)}
                    </span>
                </p>
            )}

            <div className={styles.actions}>
                {/* the real file input, visually hidden: the label below is its visible button */}
                <input
                    ref={inputRef}
                    id={inputId}
                    type="file"
                    accept={EXTENSIONS.join(",")}
                    className={styles.fileInput}
                    onChange={onChoose}
                    disabled={busy !== null}
                />
                <label htmlFor={inputId} className={styles.primaryButton} aria-disabled={busy !== null}>
                    {document ? "Replace" : "Choose file"}
                </label>
                {!document && <span className={styles.dropHint}>or drop it here</span>}
                {document && (
                    <button
                        type="button"
                        className={styles.textButton}
                        onClick={() => dialogRef.current?.showModal()}
                        disabled={busy !== null}
                    >
                        Remove
                    </button>
                )}
            </div>

            {/* announced by screen readers when it changes */}
            <p role="status" className={styles.status}>
                {busy}
            </p>
            {error && (
                <p role="alert" className={styles.error}>
                    {error}
                </p>
            )}

            {/* Removing asks first. The native <dialog> (showModal) traps focus and closes on Escape. */}
            {document && (
                <dialog ref={dialogRef} aria-labelledby={`${inputId}-dialog-title`} className={styles.dialog}>
                    <h3 id={`${inputId}-dialog-title`} className={styles.dialogTitle}>
                        Remove your {title.toLowerCase()}?
                    </h3>
                    <p className={styles.use}>
                        {document.file_name} and its {document.chunk_count} passages are deleted from OpenArt.
                    </p>
                    <div className={styles.dialogActions}>
                        <button type="button" className={styles.secondaryButton} onClick={() => dialogRef.current?.close()}>
                            Cancel
                        </button>
                        <button type="button" className={styles.dangerButton} onClick={remove}>
                            Remove
                        </button>
                    </div>
                </dialog>
            )}
        </section>
    );
};

export default DocumentSlot;
