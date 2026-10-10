"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./ClampedText.module.css";

type ClampedTextProps = {
    children: React.ReactNode;
    as?: "p" | "blockquote";
    lines?: number;          // shown before "Show more"
    className?: string;      // the text's own look (font size, weight)
};

// Long text shown as a preview: the first few lines, then "…" and a "Show more" button.
// The button appears only when the text really is longer than the preview, and the whole
// text is always in the page, so screen readers read all of it either way.
const ClampedText = ({ children, as: Tag = "p", lines = 3, className }: ClampedTextProps) => {
    const textRef = useRef<HTMLElement>(null);
    const [open, setOpen] = useState(false);
    const [overflows, setOverflows] = useState(false);

    // measured while clamped, and again when the width changes (the line count changes with it)
    useEffect(() => {
        const text = textRef.current;
        if (!text || open) {
            return;
        }
        const measure = () => setOverflows(text.scrollHeight > text.clientHeight + 1);
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(text);
        return () => observer.disconnect();
    }, [open]);

    return (
        <div className={styles.wrapper}>
            <Tag
                ref={textRef as React.Ref<HTMLParagraphElement & HTMLQuoteElement>}
                className={`${className ?? ""} ${open ? "" : styles.clamped}`}
                style={{ WebkitLineClamp: lines }}
            >
                {children}
            </Tag>
            {(overflows || open) && (
                <button
                    type="button"
                    className={styles.toggle}
                    aria-expanded={open}
                    onClick={(event) => {
                        event.preventDefault();   // inside a card: open the text, not the call
                        setOpen(!open);
                    }}
                >
                    {open ? "Show less" : "Show more"}
                </button>
            )}
        </div>
    );
};

export default ClampedText;
