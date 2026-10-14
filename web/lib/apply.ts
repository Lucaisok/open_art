// Helpers for the application page (workflow.MD, "Step 6 — Application agent")
import type { ApplicationItem } from "./types";

// How each item's state reads in the checklist: icon + words, never colour alone
export const STATES: Record<ApplicationItem["state"], { icon: string; label: string }> = {
    empty: { icon: "○", label: "Not started" },
    draft: { icon: "✎", label: "Draft, not reviewed yet" },
    confirmed: { icon: "✓", label: "Reviewed by you" },
    uploaded: { icon: "✓", label: "Uploaded" },
    chosen: { icon: "✓", label: "Images chosen" },
    ticked: { icon: "✓", label: "You have it" },
    missing: { icon: "○", label: "To get" },
};

export const DOCUMENT_NAMES: Record<string, string> = { cv: "CV", statement: "Statement", portfolio: "Portfolio" };

// A stated limit the page can count against: "max 300 words", "2,000 characters". Pages, sizes and
// formats ("max 10 pages, PDF") can't be counted in a text box, so they give null and are only shown.
export type TextLimit = { max: number; unit: "words" | "characters" };

export const textLimit = (limit: string | null | undefined): TextLimit | null => {
    const found = limit?.match(/(\d[\d,.]*)\s*(words?|characters?|chars?|signs?)/i);
    if (!found) return null;
    const max = Number(found[1].replace(/[,.]/g, ""));
    return max > 0 ? { max, unit: /^w/i.test(found[2]) ? "words" : "characters" } : null;
};

export const countText = (text: string, unit: TextLimit["unit"]): number =>
    unit === "words" ? text.split(/\s+/).filter(Boolean).length : text.length;
