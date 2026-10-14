"use client";

import { useState } from "react";
import { requestJson } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import styles from "./SaveCall.module.css";

type SaveCallProps = {
    id: string;                  // the call's id
    title: string;               // for the card's accessible name
    initial: boolean;            // saved when the page was built
    look?: "card" | "page" | "application";   // a bookmark on Discover's cards; "Save call" on the call
                                              // page; "Save / Saved to Studio" on the application page
};

// Save a call to the artist's Studio (api/saved.py), or remove it (design: DISCOVER prototype →
// Save control). A toggle button (aria-pressed): ink with a lime bookmark when saved. It changes at
// once, says so in a toast ("Saved to your calls" · View in Studio), and goes back if the server
// refuses, with the reason in the toast.
const SaveCall = ({ id, title, initial, look = "card" }: SaveCallProps) => {
    const toast = useToast();
    const [saved, setSaved] = useState(initial);
    const [busy, setBusy] = useState(false);

    const toggle = async () => {
        const next = !saved;
        setSaved(next);
        setBusy(true);
        const result = await requestJson(next ? "PUT" : "DELETE", `/api/saved/${encodeURIComponent(id)}`);
        setBusy(false);
        if (!result.ok) {
            setSaved(!next);
            toast(result.error);
            return;
        }
        if (next) toast("Saved to your calls", { href: "/studio", label: "View in Studio" });
        else toast("Removed from your calls");
    };

    const label = saved ? "Saved. Remove from your calls" : "Save call";
    return (
        <button type="button" className={`${styles.button} ${styles[look]}`} aria-pressed={saved} disabled={busy}
                aria-label={look === "card" ? `${label}: ${title}` : undefined} title={look === "card" ? label : undefined}
                onClick={toggle}>
            <svg aria-hidden="true" viewBox="0 0 24 24" className={styles.icon}>
                <path d="M6 3h12v18l-6-4.5L6 21z" fill={saved ? "#c6f432" : "none"} stroke="currentColor"
                      strokeWidth="2.6" strokeLinejoin="round" />
            </svg>
            {look === "page" && <span>{saved ? "Saved" : "Save call"}</span>}
            {look === "application" && <span>{saved ? "Saved to Studio" : "Save"}</span>}
        </button>
    );
};

export default SaveCall;
