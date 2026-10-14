import type { DocumentInfo, DocumentKind } from "@/lib/types";

// The three slots, in the Studio's order (design: STUDIO.md → Documents)
export const SLOTS: { kind: DocumentKind; label: string; hint: string }[] = [
    { kind: "cv", label: "CV", hint: "PDF, DOCX, TXT or MD" },
    { kind: "statement", label: "Artist statement", hint: "PDF, DOCX, TXT or MD" },
    { kind: "portfolio", label: "Portfolio", hint: "A PDF with images works best" },
];

const size = (bytes: number) =>
    bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

// "PDF · 240 KB · 3 Oct 2026 · 14 images"
export const documentMeta = (d: DocumentInfo) => {
    const type = d.file_name.split(".").pop()?.toUpperCase() ?? "";
    const date = new Date(d.uploaded_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    const images = d.images > 0 ? ` · ${d.images} ${d.images === 1 ? "image" : "images"}` : "";
    return `${type} · ${size(d.size_bytes)} · ${date}${images}`;
};
