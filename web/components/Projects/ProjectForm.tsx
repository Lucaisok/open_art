"use client";

import { useState } from "react";
import type { ProjectInput } from "@/lib/types";
import styles from "./Projects.module.css";

type ProjectFormProps = {
    start: ProjectInput;               // empty for "Add", a suggestion or saved project for "Edit"
    submitLabel: string;
    onSubmit: (values: ProjectInput) => Promise<string | null>;   // an error sentence, or null when saved
    onCancel: () => void;
};

const STATUSES: { value: NonNullable<ProjectInput["status"]>; label: string }[] = [
    { value: "current", label: "Now: I'm working on it" },
    { value: "planned", label: "Next: I'm planning it" },
    { value: "past", label: "Past: it's done" },
];

// Add or edit one project or interest. An interest is only its text; a project has a status and a
// title or description. The API checks the same and its sentence is shown if it refuses.
const ProjectForm = ({ start, submitLabel, onSubmit, onCancel }: ProjectFormProps) => {
    const [values, setValues] = useState<ProjectInput>(start);
    const [error, setError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const interest = values.kind === "interest";
    const set = (name: keyof ProjectInput, value: string) => setValues({ ...values, [name]: value || null });

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        setSaving(true);
        setError(await onSubmit(values));
        setSaving(false);
    };

    return (
        <form className={styles.form} onSubmit={submit}>
            {!interest && (
                <>
                    <label className={styles.field}>
                        <span className={styles.label}>Title</span>
                        <input className={styles.input} value={values.title ?? ""} maxLength={200}
                               onChange={(e) => set("title", e.target.value)} />
                    </label>
                    <fieldset className={styles.field}>
                        <legend className={styles.label}>When</legend>
                        <div className={styles.statusChoices}>
                            {STATUSES.map((status) => (
                                <label key={status.value} className={styles.statusChoice}>
                                    <input type="radio" name="status" value={status.value}
                                           checked={values.status === status.value}
                                           onChange={() => set("status", status.value)} />
                                    {status.label}
                                </label>
                            ))}
                        </div>
                    </fieldset>
                    <div className={styles.row}>
                        <label className={styles.field}>
                            <span className={styles.label}>Years</span>
                            <input className={styles.input} value={values.years ?? ""} maxLength={30}
                                   placeholder="2025, or 2024–" onChange={(e) => set("years", e.target.value)} />
                        </label>
                        <label className={styles.field}>
                            <span className={styles.label}>Medium</span>
                            <input className={styles.input} value={values.medium ?? ""} maxLength={200}
                                   placeholder="sound installation" onChange={(e) => set("medium", e.target.value)} />
                        </label>
                    </div>
                </>
            )}
            <label className={styles.field}>
                <span className={styles.label}>{interest ? "What you want to explore" : "Description"}</span>
                <textarea className={styles.textarea} value={values.summary ?? ""} maxLength={3000} rows={4}
                          onChange={(e) => set("summary", e.target.value)} />
            </label>
            {error && <p className={styles.error} role="alert">{error}</p>}
            <div className={styles.actions}>
                <button type="submit" className={styles.primary} disabled={saving}>
                    {saving ? "Saving…" : submitLabel}
                </button>
                <button type="button" className={styles.secondary} onClick={onCancel}>
                    Cancel
                </button>
            </div>
        </form>
    );
};

export default ProjectForm;
