import type { ReactNode } from "react";
import type { Evidence } from "@/lib/types";
import styles from "./ProfileEditor.module.css";

type FieldProps = {
    id: string; // the control's id (for <label>) or the group's id (for fieldsets)
    label: string;
    helper?: string; // why we ask
    error?: string;
    evidence?: Evidence; // set when the value came from the CV
    cvSays?: { value: string; quote: string; onUse: () => void }; // the CV differs from the saved value
    group?: boolean; // several controls (pills, chips): a <fieldset> with a <legend> instead of a <label>
    children: ReactNode;
};

// One form field: label, "From your CV" mark with its quote, why we ask, the control, what the CV says
// when it differs from the saved value, the error.
// The helper and the error are linked to the control with aria-describedby by the caller
// (ids `${id}-helper` and `${id}-error`).
const Field = ({ id, label, helper, error, evidence, cvSays, group = false, children }: FieldProps) => {
    const head = (
        <span className={styles.fieldHead}>
            <span className={styles.label}>{label}</span>
            {evidence && <span className={styles.fromCv}>From your CV</span>}
        </span>
    );
    const body = (
        <>
            {evidence && (
                <details className={styles.quote}>
                    <summary>Show where it says so</summary>
                    <blockquote>{evidence.quote}</blockquote>
                    <p className={styles.citation}>{evidence.citation}</p>
                </details>
            )}
            {helper && (
                <p id={`${id}-helper`} className={styles.helper}>
                    {helper}
                </p>
            )}
            {children}
            {cvSays && (
                <div className={styles.cvSays}>
                    <p>
                        Your CV says <strong>{cvSays.value}</strong>{" "}
                        <span className={styles.cvSaysQuote}>(“{cvSays.quote}”)</span>
                    </p>
                    <button type="button" className={styles.textButton} onClick={cvSays.onUse}>
                        Use this
                    </button>
                </div>
            )}
            {error && (
                <p id={`${id}-error`} className={styles.fieldError}>
                    {error}
                </p>
            )}
        </>
    );

    if (group) {
        return (
            <fieldset className={styles.field} id={id} aria-describedby={error ? `${id}-error` : undefined}>
                <legend className={styles.legend}>{head}</legend>
                {body}
            </fieldset>
        );
    }
    return (
        <div className={styles.field}>
            <label htmlFor={id} className={styles.legend}>
                {head}
            </label>
            {body}
        </div>
    );
};

export default Field;

// aria-describedby for a control inside a Field: its helper and its error, when present
export const describedBy = (id: string, helper?: string, error?: string) =>
    [helper ? `${id}-helper` : null, error ? `${id}-error` : null].filter(Boolean).join(" ") || undefined;
