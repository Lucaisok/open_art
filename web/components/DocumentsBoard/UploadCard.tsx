"use client";

import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { requestJson, uploadFile } from "@/lib/api";
import type { DocumentInfo, DocumentKind } from "@/lib/types";
import styles from "./UploadCard.module.css";

export type SlotInfo = {
    kind: DocumentKind;
    number: string; // "01"
    title: string;
    description: string;
    readResult: (passages: number) => string; // "8 passages read", shown after the file size
};

// Same limits as the API (src/rag/documents.py), checked here first so a wrong file
// is refused at once instead of after the upload
const EXTENSIONS = [".pdf", ".docx", ".txt", ".md"];
const MAX_BYTES = 10 * 1024 * 1024;
const FORMATS_LINE = "PDF, DOCX, TXT or MD, one file, up to 10 MB";

// A file on its way up. After the last byte (progress 1) the server still reads and embeds it.
type Upload = { name: string; size: number; progress: number; abort: () => void };

const formatSize = (bytes: number) =>
    bytes > 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

const extensionOf = (name: string) => (name.split(".").pop() ?? "").toUpperCase().slice(0, 4);

type UploadCardProps = {
    slot: SlotInfo;
    initialDocument: DocumentInfo | null;
    onAddedChange: (kind: DocumentKind, added: boolean) => void; // tells the board, for "N of 3 added"
    onBusyChange: (kind: DocumentKind, busy: boolean) => void; // tells the board, to disable Continue
};

// One slot of the Documents page (design: DOCUMENTS.md → Upload card). Choosing or dropping a
// file uploads it at once; a new file replaces the slot's document. × removes it (or cancels).
const UploadCard = ({ slot, initialDocument, onAddedChange, onBusyChange }: UploadCardProps) => {
    const [document, setDocument] = useState<DocumentInfo | null>(initialDocument);
    const [upload, setUpload] = useState<Upload | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [dragOver, setDragOver] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);
    const inputId = `upload-${slot.kind}`;

    const busy = upload !== null;
    useEffect(() => onAddedChange(slot.kind, document !== null), [slot.kind, document, onAddedChange]);
    useEffect(() => onBusyChange(slot.kind, busy), [slot.kind, busy, onBusyChange]);

    const start = async (file: File) => {
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
        const request = uploadFile<DocumentInfo>("PUT", `/api/documents/${slot.kind}`, file, (progress) =>
            setUpload((current) => (current ? { ...current, progress } : current)),
        );
        setUpload({ name: file.name, size: file.size, progress: 0, abort: request.abort });
        const result = await request.done;
        setUpload(null);
        if (result.ok) {
            setDocument(result.data);
        } else if (result.error !== "aborted") {
            setError(result.error); // the slot keeps its previous document, as the API does
        }
    };

    const onPick = (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        event.target.value = ""; // so the same file can be picked again
        if (file) {
            start(file);
        }
    };

    const onDrop = (event: DragEvent<HTMLElement>) => {
        event.preventDefault();
        setDragOver(false);
        const file = event.dataTransfer.files[0];
        if (file && !upload) {
            start(file);
        }
    };

    const remove = async () => {
        setError(null);
        if (upload) {
            upload.abort(); // cancels the upload; the previous document (if any) stays
            return;
        }
        if (!document) {
            return;
        }
        const result = await requestJson<null>("DELETE", `/api/documents/${slot.kind}`);
        if (result.ok || result.status === 404) {
            setDocument(null);
            inputRef.current?.focus(); // focus stays in the card: on the new "Choose file"
        } else {
            setError(result.error);
        }
    };

    // what the card shows
    const tag = upload ? "Uploading" : document ? "Added" : "Not added";
    const row = upload
        ? {
              name: upload.name,
              meta: upload.progress < 1 ? `Uploading ${Math.round(upload.progress * 100)}%` : "Reading…",
          }
        : document
          ? { name: document.file_name, meta: `${formatSize(document.size_bytes)} · ${slot.readResult(document.chunk_count)}` }
          : null;
    const cardState = dragOver ? styles.cardDragOver : row ? styles.cardFilled : styles.cardEmpty;

    return (
        <section
            aria-labelledby={`${inputId}-title`}
            className={`${styles.card} ${cardState}`}
            onDragOver={(event) => {
                event.preventDefault();
                setDragOver(true);
            }}
            onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                    setDragOver(false);
                }
            }}
            onDrop={onDrop}
        >
            <div className={styles.top}>
                <span className={styles.number} aria-hidden="true">
                    {slot.number}
                </span>
                <span
                    className={`${styles.tag} ${upload ? styles.tagUploading : document ? styles.tagAdded : styles.tagEmpty}`}
                >
                    {tag}
                </span>
            </div>
            <h2 id={`${inputId}-title`} className={styles.title}>
                {slot.title}
            </h2>
            <p className={styles.description}>{slot.description}</p>

            <div className={styles.bottom}>
                {row && (
                    <div className={styles.fileRow}>
                        <div className={styles.fileLine}>
                            <span className={styles.ext} aria-hidden="true">
                                {extensionOf(row.name)}
                            </span>
                            <div className={styles.fileText}>
                                <p className={styles.fileName} title={row.name}>
                                    {row.name}
                                </p>
                                {/* announced by screen readers as it changes: Uploading → Reading → result */}
                                <p className={styles.fileMeta} aria-live="polite">
                                    {row.meta}
                                </p>
                            </div>
                            <button
                                type="button"
                                className={styles.remove}
                                onClick={remove}
                                aria-label={upload ? `Cancel uploading ${row.name}` : `Remove ${row.name}`}
                                title={upload ? "Cancel" : "Remove"}
                            >
                                ×
                            </button>
                        </div>
                        {upload && (
                            <div className={styles.bar} aria-hidden="true">
                                <div className={styles.barFill} style={{ width: `${upload.progress * 100}%` }} />
                            </div>
                        )}
                    </div>
                )}

                {/* one file per slot: the button is shown only while the slot is empty.
                    To replace a file, drop the new one on the card or remove the old one first. */}
                {!row && (
                    <label htmlFor={inputId} className={`${styles.drop} ${dragOver ? styles.dropOver : ""}`}>
                        <input
                            ref={inputRef}
                            id={inputId}
                            type="file"
                            accept={EXTENSIONS.join(",")}
                            className={styles.fileInput}
                            onChange={onPick}
                        />
                        <span className={styles.dropLabel}>Choose file</span>
                        <span className={styles.dropHint}>or drag it here</span>
                    </label>
                )}

                {error && (
                    <p role="alert" className={styles.error}>
                        {error}
                    </p>
                )}
                <p className={styles.formats}>{FORMATS_LINE}</p>
            </div>
        </section>
    );
};

export default UploadCard;
