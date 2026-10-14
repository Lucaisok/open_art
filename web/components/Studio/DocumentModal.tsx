"use client";

import { useRef, useState } from "react";
import { uploadFile } from "@/lib/api";
import type { DocumentInfo, DocumentKind } from "@/lib/types";
import Modal from "@/components/ui/Modal";
import buttons from "@/components/ui/buttons.module.css";
import { documentMeta } from "./documents";
import styles from "./DocumentModal.module.css";

const ACCEPTED = /\.(pdf|docx|txt|md)$/i;
const MAX_BYTES = 10 * 1024 * 1024;

type DocumentModalProps = {
    kind: DocumentKind;
    label: string;                         // "CV", "Artist statement", "Portfolio"
    current: DocumentInfo | null;          // the file in the slot, if any
    onClose: () => void;
    onUploaded: (document: DocumentInfo) => void;
    onRemove: () => void;                  // asks the parent to confirm
};

// Upload or replace one document (design: STUDIO.md → Document modal): the current file with
// Remove, a drop zone (lime while a file is dragged over it) with "Choose a file", progress while
// sending, and the reason when a file is refused. The new file replaces the old one only once it
// has been read (api/documents.py), so a failed upload leaves the slot as it was.
const DocumentModal = ({ kind, label, current, onClose, onUploaded, onRemove }: DocumentModalProps) => {
    const [dragging, setDragging] = useState(false);
    const [progress, setProgress] = useState<number | null>(null);
    const [error, setError] = useState<string | null>(null);
    const abort = useRef<(() => void) | null>(null);
    const noun = kind === "cv" ? "CV" : label.toLowerCase();

    const send = async (file: File | undefined) => {
        if (!file) return;
        if (!ACCEPTED.test(file.name)) {
            setError("Upload a PDF, DOCX, TXT or MD file.");
            return;
        }
        if (file.size > MAX_BYTES) {
            setError("That file is larger than 10 MB. Compress it or split it, then try again.");
            return;
        }
        setError(null);
        setProgress(0);
        const upload = uploadFile<DocumentInfo>("PUT", `/api/documents/${kind}`, file, setProgress);
        abort.current = upload.abort;
        const result = await upload.done;
        abort.current = null;
        setProgress(null);
        if (!result.ok) {
            if (result.error !== "aborted") setError(result.error);
            return;
        }
        onUploaded(result.data);
    };

    const sending = progress !== null;
    const percent = Math.round((progress ?? 0) * 100);
    return (
        <Modal
            title={`${current ? "Replace" : "Upload"} ${current ? "your " : ""}${noun}`}
            onClose={() => {
                abort.current?.();
                onClose();
            }}
            footer={<button type="button" className={buttons.secondary} onClick={() => { abort.current?.(); onClose(); }}>Cancel</button>}
        >
            {current && (
                <div className={styles.current}>
                    <span className={styles.file}>
                        <span className={styles.name}>{current.file_name}</span>
                        <span className={styles.meta}>{documentMeta(current)}</span>
                    </span>
                    <button type="button" className={buttons.link} onClick={onRemove} disabled={sending}>Remove</button>
                </div>
            )}
            <label
                className={`${styles.drop} ${dragging ? styles.dragging : ""} ${error ? styles.refused : ""}`}
                onDragOver={(event) => {
                    event.preventDefault();
                    setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                    event.preventDefault();
                    setDragging(false);
                    if (!sending) send(event.dataTransfer.files[0]);
                }}
            >
                <span className={styles.dropTitle}>{dragging ? "Drop to upload" : "Drag a file here"}</span>
                <span className={styles.meta}>PDF, DOCX, TXT or MD · up to 10 MB</span>
                <span className={styles.choose}>Choose a file</span>
                <input type="file" accept=".pdf,.docx,.txt,.md" className={styles.input} disabled={sending}
                       onChange={(event) => {
                           send(event.target.files?.[0]);
                           event.target.value = "";
                       }} />
            </label>
            {sending && (
                <div className={styles.progress} aria-live="polite">
                    <span className={styles.progressLine}>
                        <span>{percent < 100 ? "Uploading…" : "Reading text…"}</span>
                        <span>{percent < 100 ? `${percent}%` : ""}</span>
                    </span>
                    <span className={styles.track}><span className={styles.bar} style={{ width: `${percent}%` }} /></span>
                </div>
            )}
            {error && <p role="alert" className={styles.error}>{error}</p>}
            <p className={styles.meta}>
                One file can hold everything. If your CV includes your portfolio, upload it once: OpenArt reads both.
            </p>
        </Modal>
    );
};

export default DocumentModal;
