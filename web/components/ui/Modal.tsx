"use client";

import { useEffect, useRef, type ReactNode } from "react";
import styles from "./Modal.module.css";

type ModalProps = {
    title: string;
    onClose: () => void;
    children: ReactNode;
    footer?: ReactNode;          // the buttons, right-aligned in a sticky bar (a destructive link goes first)
    size?: "md" | "sm" | "lg";   // 680 px, 460 px for confirmations, 820 px for the image picker
    subtitle?: string;           // a line under the title ("Still photo of the film · 1 image, JPG")
    busy?: boolean;              // while saving: Esc and the backdrop don't close it
};

// Every modal of the Studio (design: STUDIO.md → Modal pattern): title and ×, a body that scrolls,
// a sticky footer. A native <dialog> opened with showModal(): it keeps the keyboard focus inside,
// hides the page from screen readers and closes on Esc. A click on the backdrop closes it too.
// Full screen on a phone.
const Modal = ({ title, subtitle, onClose, children, footer, size = "md", busy = false }: ModalProps) => {
    const ref = useRef<HTMLDialogElement>(null);
    useEffect(() => {
        const dialog = ref.current;
        if (dialog && !dialog.open) {
            dialog.showModal();
        }
        return () => dialog?.close();
    }, []);
    return (
        <dialog
            ref={ref}
            className={`${styles.dialog} ${size === "sm" ? styles.small : size === "lg" ? styles.large : ""}`}
            aria-labelledby="modal-title"
            onCancel={(event) => {
                event.preventDefault();   // Esc: closing is the parent's decision (it unmounts us)
                if (!busy) onClose();
            }}
            onClick={(event) => {
                if (event.target === ref.current && !busy) onClose();   // the backdrop, not the box
            }}
        >
            <div className={styles.box}>
                <div className={styles.head}>
                    <span className={styles.heading}>
                        <h2 id="modal-title" className={styles.title}>{title}</h2>
                        {subtitle && <span className={styles.subtitle}>{subtitle}</span>}
                    </span>
                    <button type="button" className={styles.close} onClick={onClose} aria-label="Close" disabled={busy}>
                        ×
                    </button>
                </div>
                <div className={styles.body}>{children}</div>
                {footer && <div className={styles.footer}>{footer}</div>}
            </div>
        </dialog>
    );
};

export default Modal;
