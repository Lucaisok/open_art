"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import styles from "./Toast.module.css";

type ToastMessage = { text: string; link?: { href: string; label: string } };

const ToastContext = createContext<(text: string, link?: ToastMessage["link"]) => void>(() => {});

// "Saved to your calls", "Project saved"…: one short confirmation at the bottom centre for 2.6 s
// (design: STUDIO.md → Toasts). role=status reads it out without moving the focus.
export const useToast = () => useContext(ToastContext);

const ToastProvider = ({ children }: { children: ReactNode }) => {
    const [message, setMessage] = useState<ToastMessage | null>(null);
    const timer = useRef<number | undefined>(undefined);
    const show = useCallback((text: string, link?: ToastMessage["link"]) => {
        setMessage({ text, link });
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setMessage(null), link ? 5000 : 2600);   // time to reach the link
    }, []);
    useEffect(() => () => window.clearTimeout(timer.current), []);
    return (
        <ToastContext.Provider value={show}>
            {children}
            <div role="status" className={styles.region}>
                {message && (
                    <div className={styles.toast}>
                        <span aria-hidden="true" className={styles.tick}>✓</span>
                        <span>{message.text}</span>
                        {message.link && (
                            <Link href={message.link.href} className={styles.link}>
                                {message.link.label}
                            </Link>
                        )}
                    </div>
                )}
            </div>
        </ToastContext.Provider>
    );
};

export default ToastProvider;
