import type { ReactNode } from "react";
import type { Evidence } from "@/lib/types";
import styles from "./ProfileEditor.module.css";

const SOURCE_NAMES: Record<string, string> = { cv: "CV", statement: "statement", portfolio: "portfolio" };

type CvSays = {
    value: string;
    quote: string;
    source: string;
    citation?: string;
    onUse: () => void;
    onKeep?: () => void; // "Keep mine": hide the document's value, the saved one stays
};

type FieldProps = {
    id: string; // the control's id (for <label>); a fieldset gets `${id}-group`, so it never clashes with a control
    label: string;
    helper?: string; // why we ask
    error?: string;
    evidence?: Evidence; // set when the value came from a document
    cvSays?: CvSays; // a document differs from the saved value
    group?: boolean; // several controls (pills, chips): a <fieldset> with a <legend> instead of a <label>
    full?: boolean; // takes the whole row of the section's two-column grid
    children: ReactNode;
};

// One form field (design: OpenArt Profile prototype): label and why we ask, the control, then
// "From your CV" with the line it came from (one click away), what a document says when it
// differs from the saved value, and the error. The helper and the error are linked to the
// control with aria-describedby by the caller (ids `${id}-helper` and `${id}-error`).
const Field = ({ id, label, helper, error, evidence, cvSays, group = false, full = false, children }: FieldProps) => {
    const body = (
        <>
            {helper && (
                <p id={`${id}-helper`} className={styles.helper}>
                    {helper}
                </p>
            )}
            {children}
            {evidence && (
                <details className={styles.source}>
                    <summary className={styles.sourceSummary}>
                        <span className={styles.sourceMark}>
                            <span className={styles.limeDot} aria-hidden="true" />
                            From your {SOURCE_NAMES[evidence.source ?? "cv"] ?? "documents"}
                        </span>
                        {/* the summary's text follows the open state, in CSS */}
                        <span className={styles.sourceToggle}>
                            <span className={styles.whenClosed}>Show where it says so</span>
                            <span className={styles.whenOpen}>Hide the line</span>
                        </span>
                    </summary>
                    <div className={styles.quote}>
                        <blockquote>“{evidence.quote}”</blockquote>
                        {evidence.citation && <p className={styles.citation}>{evidence.citation}</p>}
                    </div>
                </details>
            )}
            {cvSays && (
                <div className={styles.cvSays}>
                    <p className={styles.cvSaysValue}>
                        Your {SOURCE_NAMES[cvSays.source] ?? "CV"} says <strong>{cvSays.value}</strong>
                    </p>
                    <p className={styles.cvSaysQuote}>
                        “{cvSays.quote}”{" "}
                        {cvSays.citation && <span className={styles.citation}>{cvSays.citation}</span>}
                    </p>
                    <span className={styles.cvSaysActions}>
                        <button type="button" className={styles.smallButton} onClick={cvSays.onUse}>
                            Use this
                        </button>
                        {cvSays.onKeep && (
                            <button type="button" className={styles.textButton} onClick={cvSays.onKeep}>
                                Keep mine
                            </button>
                        )}
                    </span>
                </div>
            )}
            {error && (
                <p id={`${id}-error`} className={styles.fieldError}>
                    {error}
                </p>
            )}
        </>
    );

    const className = `${styles.field} ${full ? styles.fieldFull : ""}`;
    if (group) {
        return (
            <fieldset className={className} id={`${id}-group`} aria-describedby={error ? `${id}-error` : undefined}>
                <legend className={styles.label}>{label}</legend>
                {body}
            </fieldset>
        );
    }
    return (
        <div className={className}>
            <label htmlFor={id} className={styles.label}>
                {label}
            </label>
            {body}
        </div>
    );
};

export default Field;

// aria-describedby for a control inside a Field: its helper and its error, when present
export const describedBy = (id: string, helper?: string, error?: string) =>
    [helper ? `${id}-helper` : null, error ? `${id}-error` : null].filter(Boolean).join(" ") || undefined;
