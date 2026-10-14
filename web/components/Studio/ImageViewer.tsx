"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./ImageViewer.module.css";

type ImageViewerProps = {
    title: string;                       // the project's
    images: { url: string; alt: string }[];
    start: number;                       // the image clicked
    onClose: () => void;
};

// A project's images, full screen on ink (design: STUDIO.md → Image viewer): "Image n of N",
// ← → buttons and arrow keys, Esc closes. A native <dialog>, like Modal.
const ImageViewer = ({ title, images, start, onClose }: ImageViewerProps) => {
    const ref = useRef<HTMLDialogElement>(null);
    const [index, setIndex] = useState(start);
    const step = (by: number) => setIndex((i) => (i + by + images.length) % images.length);
    useEffect(() => {
        const dialog = ref.current;
        if (dialog && !dialog.open) dialog.showModal();
        return () => dialog?.close();
    }, []);
    const image = images[index];
    return (
        <dialog
            ref={ref}
            className={styles.viewer}
            aria-label="Image viewer"
            onCancel={(event) => {
                event.preventDefault();
                onClose();
            }}
            onKeyDown={(event) => {
                if (event.key === "ArrowLeft") step(-1);
                if (event.key === "ArrowRight") step(1);
            }}
        >
            <div className={styles.top}>
                <span className={styles.heading}>
                    <span className={styles.title}>{title}</span>
                    <span className={styles.count} aria-live="polite">
                        Image {index + 1} of {images.length}
                    </span>
                </span>
                <button type="button" className={styles.close} onClick={onClose} aria-label="Close">
                    ×
                </button>
            </div>
            <div className={styles.stage}>
                <button type="button" className={styles.arrow} onClick={() => step(-1)} aria-label="Previous image"
                        disabled={images.length < 2}>
                    ←
                </button>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {image && <img src={image.url} alt={image.alt} className={styles.image} />}
                <button type="button" className={styles.arrow} onClick={() => step(1)} aria-label="Next image"
                        disabled={images.length < 2}>
                    →
                </button>
            </div>
        </dialog>
    );
};

export default ImageViewer;
