"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { requestJson } from "@/lib/api";
import type { ProfileData, ProfileOptions, ProfileValues, Suggestion } from "@/lib/types";
import { MultiChoice, SingleChoice } from "./Choices";
import CountryChips from "./CountryChips";
import CvBanner from "./CvBanner";
import DateParts from "./DateParts";
import Field, { describedBy } from "./Field";
import {
    APPLICANT_TYPES,
    CAREER_STAGE_LABELS,
    FIELD_LABELS,
    formatValue,
    type EvidenceMap,
    type FieldName,
} from "./fields";
import styles from "./ProfileEditor.module.css";

type ProfileEditorProps = {
    initial: ProfileData;
    options: ProfileOptions;
    cvName: string | null;
};

type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "error"; message: string };

const THIS_YEAR = new Date().getFullYear();

// why we ask, shown under each label
const HELPERS: Partial<Record<FieldName, string>> = {
    birth_date: "Many calls have age limits.",
    nationalities: "Some calls are only for citizens of certain countries. Add every citizenship you hold.",
    residence_country: "Many calls require living in a country or region.",
    disciplines: "Calls are usually for one or a few disciplines.",
    career_stage: "Your own call. Some calls are only for emerging artists, others for established ones.",
    active_since: "The year of your first public professional work: an exhibition, performance, residency or award.",
    applicant_type: "Some calls are for individuals only, others for groups or organisations.",
    has_degree: "Some calls ask for a degree in the arts.",
    graduation_year: "Some calls are for recent graduates.",
    currently_enrolled: "Some calls are only for students, others exclude them.",
};

// "" in a number field means "not said"
const toYear = (text: string): number | null => (text.trim() === "" ? null : Number.parseInt(text, 10));

const isEmpty = (value: unknown) =>
    value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

// The form's starting point: the saved profile, with the suggestions read from the artist's documents
// filled into the fields that are still empty. A saved value is never overwritten: where the
// CV says something else, the suggestion is kept aside and shown under the field.
const startingPoint = (initial: ProfileData) => {
    const values: ProfileValues = { ...initial.values };
    const evidence: EvidenceMap = { ...(initial.evidence ?? {}) };
    const differing: Partial<Record<FieldName, Suggestion>> = {};
    let filled = 0;
    for (const suggestion of initial.suggestions?.items ?? []) {
        const field = suggestion.field as FieldName;
        if (!(field in FIELD_LABELS)) {
            continue;
        }
        const current = values[field];
        if (isEmpty(current)) {
            values[field] = suggestion.value as never;
            evidence[field] = { quote: suggestion.quote, citation: suggestion.citation, source: suggestion.source };
            filled++;
        } else if (JSON.stringify(current) !== JSON.stringify(suggestion.value)) {
            differing[field] = suggestion;
        }
    }
    return { values, evidence, differing, filled };
};

// The profile page: what the CV filled in (banner), the form (three groups), and a footer bar
// with Save. Only Save writes anything (PUT /api/profile): the values from documents are suggestions
// until then, and Save also marks this CV as reviewed so they aren't filled in again.
const ProfileEditor = ({ initial, options, cvName }: ProfileEditorProps) => {
    const [start] = useState(() => startingPoint(initial));
    const [values, setValues] = useState<ProfileValues>(start.values);
    const [evidence, setEvidence] = useState<EvidenceMap>(start.evidence);
    const [differing, setDiffering] = useState(start.differing);
    // documents whose suggestions are shown and not yet saved after
    const [reviewing, setReviewing] = useState<string[]>(() => initial.suggestions?.documents.map((d) => d.id) ?? []);
    const [saved, setSaved] = useState(() => JSON.stringify({ values: initial.values, evidence: initial.evidence ?? {} }));
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });
    const [birthIncomplete, setBirthIncomplete] = useState(false); // some date boxes filled, not all
    const neverSaved = initial.updated_at === null && saveState.kind !== "saved";

    // unsaved: values changed, or the documents' suggestions still need the artist's Save
    const dirty = useMemo(
        () => JSON.stringify({ values, evidence }) !== saved || reviewing.length > 0,
        [values, evidence, saved, reviewing],
    );

    // leaving with unsaved changes: the browser asks first
    useEffect(() => {
        if (!dirty) {
            return;
        }
        const warn = (event: BeforeUnloadEvent) => event.preventDefault();
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, [dirty]);

    // a change by hand: new value, the field's CV quote and error go
    const set = <K extends FieldName>(field: K, value: ProfileValues[K]) => {
        setValues((prev) => ({ ...prev, [field]: value }));
        setEvidence((prev) => {
            if (!(field in prev)) {
                return prev;
            }
            const next = { ...prev };
            delete next[field];
            return next;
        });
        setDiffering((prev) => {
            if (!(field in prev)) {
                return prev;
            }
            const next = { ...prev };
            delete next[field];
            return next;
        });
        setErrors((prev) => ({ ...prev, [field]: "" }));
        setSaveState({ kind: "idle" });
        if (field === "birth_date") {
            setBirthIncomplete(false); // a full date (or none) was just set
        }
    };

    // "Use this": the CV's value instead of the saved one, with its quote
    const takeCvValue = (field: FieldName) => {
        const suggestion = differing[field];
        if (!suggestion) {
            return;
        }
        set(field, suggestion.value as never);
        setEvidence((prev) => ({
            ...prev,
            [field]: { quote: suggestion.quote, citation: suggestion.citation, source: suggestion.source },
        }));
    };

    const save = async (event?: FormEvent) => {
        event?.preventDefault();
        if (birthIncomplete) {
            // checked here: a half-typed date never reaches the form's values
            setErrors((prev) => ({ ...prev, birth_date: "Enter the full date: day, month and year." }));
            setSaveState({ kind: "error", message: "Fix the field marked above." });
            document.getElementById("field-birth_date")?.focus();
            return;
        }
        setSaveState({ kind: "saving" });
        const result = await requestJson<ProfileData>("PUT", "/api/profile", {
            values,
            evidence,
            reviewed_documents: reviewing,
        });
        if (!result.ok) {
            setErrors(result.fieldErrors);
            const count = Object.keys(result.fieldErrors).length;
            setSaveState({
                kind: "error",
                message: count > 0 ? `Fix the ${count === 1 ? "field" : `${count} fields`} marked above.` : result.error,
            });
            const first = Object.keys(result.fieldErrors)[0];
            if (first) {
                // the control itself, or the first control of a group (pills, chips)
                const target =
                    document.getElementById(`field-${first}`) ??
                    document.querySelector<HTMLElement>(`#field-${first}-group input, #field-${first}-group select`);
                target?.focus();
            }
            return;
        }
        // the API returns the values as stored (normalised), which become the new baseline
        setValues(result.data.values);
        setEvidence(result.data.evidence ?? {});
        setSaved(JSON.stringify({ values: result.data.values, evidence: result.data.evidence ?? {} }));
        setReviewing([]);
        setDiffering({});
        setErrors({});
        setSaveState({ kind: "saved" });
    };

    // shorthand for the props every Field and its control share
    const field = (name: FieldName) => {
        const fromCv = differing[name];
        return {
            id: `field-${name}`,
            label: FIELD_LABELS[name],
            helper: HELPERS[name],
            error: errors[name] || undefined,
            evidence: evidence[name],
            cvSays: fromCv
                ? {
                      value: formatValue(name, fromCv.value, options) ?? "",
                      quote: fromCv.quote,
                      source: fromCv.source,
                      onUse: () => takeCvValue(name),
                  }
                : undefined,
        };
    };
    const ariaFor = (name: FieldName) => ({
        "aria-describedby": describedBy(`field-${name}`, HELPERS[name], errors[name] || undefined),
        "aria-invalid": errors[name] ? true : undefined,
    });

    const yearsActive =
        values.active_since && values.active_since >= 1900 && values.active_since <= THIS_YEAR
            ? THIS_YEAR - values.active_since
            : null;

    const status =
        saveState.kind === "saving"
            ? "Saving…"
            : saveState.kind === "error"
              ? saveState.message
              : reviewing.length > 0 && start.filled > 0 && JSON.stringify({ values, evidence }) === JSON.stringify({ values: start.values, evidence: start.evidence })
                ? "Filled in from your documents, not saved yet"
                : dirty
                ? "Unsaved changes"
                : saveState.kind === "saved"
                  ? "Saved"
                  : neverSaved
                    ? "Not saved yet"
                    : "All changes saved";

    return (
        <>
            <main id="main" className={styles.main}>
                <h1 className={styles.title}>
                    Your profile<span className={styles.stop}>.</span>
                </h1>
                <p className={styles.intro}>
                    The facts calls are checked against. Every field is optional: an empty one never rules you out,
                    we just flag it for you to check.
                </p>

                <div className={styles.layout}>
                    <CvBanner
                        cvName={cvName}
                        documents={initial.suggestions?.documents.map((d) => d.file_name) ?? []}
                        found={initial.suggestions ? initial.suggestions.items.length : null}
                        filled={start.filled}
                        differing={Object.keys(start.differing).length}
                    />

                    <form id="profile-form" className={styles.form} onSubmit={save} noValidate>
                        <section className={styles.group} aria-labelledby="group-about">
                            <div className={styles.groupHead}>
                                <span className={styles.groupNumber} aria-hidden="true">
                                    01
                                </span>
                                <h2 id="group-about" className={styles.groupTitle}>
                                    About you
                                </h2>
                            </div>
                            <div className={styles.groupFields}>

                            <Field {...field("birth_date")} group>
                                <DateParts
                                    id="field-birth_date"
                                    value={values.birth_date ?? null}
                                    onChange={(v) => set("birth_date", v)}
                                    onIncomplete={setBirthIncomplete}
                                    describedBy={ariaFor("birth_date")["aria-describedby"]}
                                    invalid={Boolean(errors.birth_date)}
                                />
                            </Field>

                            <Field {...field("nationalities")}>
                                <CountryChips
                                    id="field-nationalities"
                                    codes={values.nationalities ?? []}
                                    countries={options.countries}
                                    onChange={(codes) => set("nationalities", codes)}
                                    describedBy={ariaFor("nationalities")["aria-describedby"]}
                                />
                            </Field>

                            <Field {...field("residence_country")}>
                                <select
                                    id="field-residence_country"
                                    className={`${styles.input} ${styles.select}`}
                                    value={values.residence_country ?? ""}
                                    onChange={(e) => set("residence_country", e.target.value || null)}
                                    {...ariaFor("residence_country")}
                                >
                                    <option value="">Not said</option>
                                    {options.countries.map((c) => (
                                        <option key={c.code} value={c.code}>
                                            {c.name}
                                        </option>
                                    ))}
                                </select>
                            </Field>
                            </div>
                        </section>

                        <section className={styles.group} aria-labelledby="group-practice">
                            <div className={styles.groupHead}>
                                <span className={styles.groupNumber} aria-hidden="true">
                                    02
                                </span>
                                <h2 id="group-practice" className={styles.groupTitle}>
                                    Practice
                                </h2>
                            </div>
                            <div className={styles.groupFields}>

                            <Field {...field("disciplines")} group>
                                <MultiChoice
                                    name="disciplines"
                                    options={options.disciplines}
                                    values={values.disciplines ?? []}
                                    onChange={(list) => set("disciplines", list)}
                                />
                            </Field>

                            <Field {...field("career_stage")} group>
                                <SingleChoice
                                    name="career_stage"
                                    options={options.career_stages.map((s) => ({
                                        value: s,
                                        label: CAREER_STAGE_LABELS[s] ?? s,
                                    }))}
                                    value={values.career_stage ?? null}
                                    onChange={(v) => set("career_stage", v)}
                                />
                            </Field>

                            <Field {...field("active_since")}>
                                <div className={styles.yearRow}>
                                    <input
                                        id="field-active_since"
                                        type="number"
                                        inputMode="numeric"
                                        className={`${styles.input} ${styles.inputYear}`}
                                        min={1900}
                                        max={THIS_YEAR}
                                        placeholder="e.g. 2016"
                                        value={values.active_since ?? ""}
                                        onChange={(e) => set("active_since", toYear(e.target.value))}
                                        {...ariaFor("active_since")}
                                    />
                                    {yearsActive !== null && (
                                        <span className={styles.yearNote}>
                                            {yearsActive} {yearsActive === 1 ? "year" : "years"} of practice
                                        </span>
                                    )}
                                </div>
                            </Field>

                            <Field {...field("applicant_type")} group>
                                <SingleChoice
                                    name="applicant_type"
                                    options={APPLICANT_TYPES.map((t) => ({ value: t.value, label: t.label }))}
                                    value={values.applicant_type ?? null}
                                    onChange={(v) => set("applicant_type", v)}
                                />
                            </Field>
                            </div>
                        </section>

                        <section className={styles.group} aria-labelledby="group-education">
                            <div className={styles.groupHead}>
                                <span className={styles.groupNumber} aria-hidden="true">
                                    03
                                </span>
                                <h2 id="group-education" className={styles.groupTitle}>
                                    Education
                                </h2>
                            </div>
                            <div className={styles.groupFields}>

                            <Field {...field("has_degree")} group>
                                <SingleChoice
                                    name="has_degree"
                                    look="switch"
                                    options={[
                                        { value: true, label: "Yes" },
                                        { value: false, label: "No" },
                                    ]}
                                    value={values.has_degree ?? null}
                                    onChange={(v) => {
                                        set("has_degree", v);
                                        if (v === false) {
                                            // no degree: its field and year no longer apply
                                            set("degree_field", null);
                                            set("graduation_year", null);
                                        }
                                    }}
                                />
                            </Field>

                            {values.has_degree !== false && (
                                <>
                                    <Field {...field("degree_field")}>
                                        <input
                                            id="field-degree_field"
                                            type="text"
                                            className={styles.input}
                                            maxLength={200}
                                            placeholder="e.g. Painting and Graphic Arts"
                                            value={values.degree_field ?? ""}
                                            onChange={(e) => set("degree_field", e.target.value || null)}
                                            {...ariaFor("degree_field")}
                                        />
                                    </Field>

                                    <Field {...field("graduation_year")}>
                                        <input
                                            id="field-graduation_year"
                                            type="number"
                                            inputMode="numeric"
                                            className={`${styles.input} ${styles.inputYear}`}
                                            min={1900}
                                            max={THIS_YEAR}
                                            placeholder="e.g. 2021"
                                            value={values.graduation_year ?? ""}
                                            onChange={(e) => set("graduation_year", toYear(e.target.value))}
                                            {...ariaFor("graduation_year")}
                                        />
                                    </Field>
                                </>
                            )}

                            <Field {...field("currently_enrolled")} group>
                                <SingleChoice
                                    name="currently_enrolled"
                                    look="switch"
                                    options={[
                                        { value: true, label: "Yes" },
                                        { value: false, label: "No" },
                                    ]}
                                    value={values.currently_enrolled ?? null}
                                    onChange={(v) => set("currently_enrolled", v)}
                                />
                            </Field>
                            </div>
                        </section>
                    </form>
                </div>
            </main>

            <footer className={styles.footer}>
                <div className={styles.footerLeft}>
                    <Link href="/documents" className={styles.back}>
                        ← Back
                    </Link>
                    <p
                        className={`${styles.saveStatus} ${saveState.kind === "error" ? styles.saveStatusError : ""}`}
                        role={saveState.kind === "error" ? "alert" : "status"}
                    >
                        {status}
                    </p>
                </div>
                {/* everything saved: the onboarding is done, on to the calls */}
                {!dirty && !neverSaved ? (
                    <Link href="/discover" className={styles.saveButton}>
                        Continue to Discover →
                    </Link>
                ) : (
                    <button
                        type="submit"
                        form="profile-form"
                        className={styles.saveButton}
                        disabled={!dirty || saveState.kind === "saving"}
                    >
                        {saveState.kind === "saving" ? "Saving…" : "Save profile"}
                    </button>
                )}
            </footer>
        </>
    );
};

export default ProfileEditor;
