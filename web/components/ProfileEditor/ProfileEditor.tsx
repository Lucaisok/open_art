"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { requestJson } from "@/lib/api";
import { forgetSearch } from "@/lib/discover";
import SetupSteps from "@/components/Onboarding/SetupSteps";
import onboarding from "@/components/Onboarding/Onboarding.module.css";
import buttons from "@/components/ui/buttons.module.css";
import type { ProfileData, ProfileOptions, ProfileValues, Suggestion } from "@/lib/types";
import { MultiChoice, SingleChoice } from "./Choices";
import CountryChips from "./CountryChips";
import SchoolsEditor from "./SchoolsEditor";
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
    hasDocuments: boolean;   // any document uploaded (one file may be CV, statement and portfolio at once)
};

// "error": `fields` of them need fixing (0: the save itself failed)
type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "error"; fields: number };

const THIS_YEAR = new Date().getFullYear();

// why we ask, shown under each label
export const HELPERS: Partial<Record<FieldName, string>> = {
    name: "Shown in your Studio. Not used to check calls.",
    birth_date: "Many calls have age limits.",
    nationalities: "Some calls are only for citizens of certain countries. Add every citizenship you hold.",
    residence_country: "Many calls require living in a country or region.",
    residence_city: "Some calls are for artists based in one city, like Berlin or Paris.",
    languages: "Languages you can work in at a fluent or professional level. Some calls require one.",
    disciplines: "Calls are usually for one or a few disciplines.",
    career_stage: "Your own call. Some calls are only for emerging artists, others for established ones.",
    active_since: "The year of your first public professional work: an exhibition, performance, residency or award.",
    applicant_type: "Some calls are for individuals only, others for groups or organisations.",
    has_degree: "Some calls ask for a degree in the arts.",
    graduation_year: "Some calls are for recent graduates.",
    currently_enrolled: "Some calls are only for students, others exclude them.",
    education: "Some calls are for alumni of a school, or for people who studied in a country or region.",
};

// "" in a number field means "not said"
export const toYear = (text: string): number | null => (text.trim() === "" ? null : Number.parseInt(text, 10));

export const isEmpty = (value: unknown) =>
    value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

// The form's starting point: the saved profile, with the suggestions read from the artist's documents
// filled into the fields that are still empty. A saved value is never overwritten: where the
// CV says something else, the suggestion is kept aside and shown under the field.
export const startingPoint = (initial: ProfileData) => {
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

// Onboarding step 2 (design: OpenArt Profile prototype): the setup steps, what the documents filled
// in (banner), the form in three sections of field rows, and a fixed bar with the save status and
// Save. Only Save writes anything (PUT /api/profile): the values from documents are suggestions until
// then, and Save also marks the documents as reviewed so they aren't filled in again. Once saved,
// the bar leads on to Projects (step 3). After the onboarding the profile is edited in the Studio.
const ProfileEditor = ({ initial, options, hasDocuments }: ProfileEditorProps) => {
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

    // "Keep mine": the saved value stays, the document's one is no longer shown
    const keepMine = (field: FieldName) =>
        setDiffering((prev) => {
            const next = { ...prev };
            delete next[field];
            return next;
        });

    const save = async (event?: FormEvent) => {
        event?.preventDefault();
        if (birthIncomplete) {
            // checked here: a half-typed date never reaches the form's values
            setErrors((prev) => ({ ...prev, birth_date: "Enter a full date: day, month and a four-digit year." }));
            setSaveState({ kind: "error", fields: 1 });
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
            setSaveState({ kind: "error", fields: Object.keys(result.fieldErrors).length });
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
        forgetSearch(); // Discover starts again from the saved profile's disciplines
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
                      citation: fromCv.citation,
                      onUse: () => takeCvValue(name),
                      onKeep: () => keepMine(name),
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


    // "3 of 5 filled" in each section's head: the fields shown in it that have a value
    const filledLabel = (names: FieldName[]) =>
        `${names.filter((name) => !isEmpty(values[name])).length} of ${names.length} filled`;
    const degreeFields: FieldName[] = values.has_degree !== false ? ["degree_field", "graduation_year"] : [];
    const sections = {
        about: ["name", "birth_date", "nationalities", "residence_country", "residence_city", "languages"] as FieldName[],
        practice: ["disciplines", "career_stage", "active_since", "applicant_type"] as FieldName[],
        education: ["has_degree", ...degreeFields, "education", "currently_enrolled"] as FieldName[],
    };
    const sectionHead = (id: string, number: string, title: string, names: FieldName[]) => (
        <div className={styles.sectionHead}>
            <h2 id={id} className={styles.sectionTitle}>
                {number} · {title}
            </h2>
            <span className={styles.sectionFilled}>{filledLabel(names)}</span>
        </div>
    );

    // a year typed as text: digits only, four at most
    const yearInput = (name: "active_since" | "graduation_year") => (
        <input
            id={`field-${name}`}
            type="text"
            inputMode="numeric"
            maxLength={4}
            className={`${styles.input} ${styles.inputYear}`}
            placeholder="YYYY"
            value={values[name] ?? ""}
            onChange={(e) => set(name, toYear(e.target.value.replace(/\D/g, "")))}
            {...ariaFor(name)}
        />
    );

    // the bar's status, with its square marker: empty, half ink (unsaved), lime (saved), red (a problem)
    const untouchedSuggestions =
        reviewing.length > 0 &&
        start.filled > 0 &&
        JSON.stringify({ values, evidence }) === JSON.stringify({ values: start.values, evidence: start.evidence });
    const [status, marker] =
        saveState.kind === "saving"
            ? ["Saving…", ""]
            : saveState.kind === "error"
              ? saveState.fields > 0
                  ? [`${saveState.fields} ${saveState.fields === 1 ? "field needs" : "fields need"} fixing`, styles.dotRed]
                  : ["Couldn't save your profile. Try again.", styles.dotRed]
              : untouchedSuggestions
                ? ["Filled in from your documents, not saved yet", styles.dotHalf]
                : dirty
                  ? ["Unsaved changes", styles.dotHalf]
                  : neverSaved
                    ? ["Not saved yet", ""]
                    : ["All changes saved", styles.dotOn];
    const allSaved = !dirty && !neverSaved;

    return (
        <main id="main" className={onboarding.main}>
            <SetupSteps current={1} />
            <div className={onboarding.intro}>
                <h1 className={onboarding.title}>Your profile</h1>
                <p className={onboarding.lead}>
                    The facts calls are checked against. Every field is optional: an empty one never rules you out,
                    we just flag it for you to check.
                </p>
            </div>

            <CvBanner
                hasDocuments={hasDocuments}
                documents={initial.suggestions?.documents.map((d) => d.file_name) ?? []}
                found={initial.suggestions ? initial.suggestions.items.length : null}
                filled={start.filled}
                differing={Object.keys(differing).map((name) => FIELD_LABELS[name as FieldName])}
            />

            <form id="profile-form" onSubmit={save} noValidate>
                <section className={styles.section} aria-labelledby="group-about">
                    {sectionHead("group-about", "01", "About you", sections.about)}
                    <div className={styles.fields}>
                        <Field {...field("name")}>
                            <input
                                id="field-name"
                                type="text"
                                className={styles.input}
                                maxLength={120}
                                autoComplete="name"
                                placeholder="As you sign your work"
                                value={values.name ?? ""}
                                onChange={(e) => set("name", e.target.value || null)}
                                {...ariaFor("name")}
                            />
                        </Field>

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
                                <option value="">Not set</option>
                                {options.countries.map((c) => (
                                    <option key={c.code} value={c.code}>
                                        {c.name}
                                    </option>
                                ))}
                            </select>
                        </Field>

                        <Field {...field("residence_city")}>
                            <input
                                id="field-residence_city"
                                type="text"
                                className={styles.input}
                                maxLength={100}
                                autoComplete="address-level2"
                                placeholder="e.g. Berlin"
                                value={values.residence_city ?? ""}
                                onChange={(e) => set("residence_city", e.target.value || null)}
                                {...ariaFor("residence_city")}
                            />
                        </Field>

                        <Field {...field("languages")}>
                            <CountryChips
                                id="field-languages"
                                noun="language"
                                codes={values.languages ?? []}
                                countries={options.languages}
                                onChange={(codes) => set("languages", codes)}
                                describedBy={ariaFor("languages")["aria-describedby"]}
                            />
                        </Field>
                    </div>
                </section>

                <section className={styles.section} aria-labelledby="group-practice">
                    {sectionHead("group-practice", "02", "Practice", sections.practice)}
                    <div className={styles.fields}>
                        <Field {...field("disciplines")} group full>
                            <MultiChoice
                                name="disciplines"
                                options={options.disciplines}
                                values={values.disciplines ?? []}
                                onChange={(list) => set("disciplines", list)}
                            />
                        </Field>

                        <Field {...field("career_stage")} group full>
                            <SingleChoice
                                name="career_stage"
                                withNone={false}
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
                                {yearInput("active_since")}
                                {yearsActive !== null && (
                                    <span className={styles.yearNote}>
                                        {yearsActive === 0
                                            ? "This year"
                                            : `${yearsActive} ${yearsActive === 1 ? "year" : "years"}`}
                                    </span>
                                )}
                            </div>
                        </Field>

                        <Field {...field("applicant_type")} group>
                            <SingleChoice
                                name="applicant_type"
                                withNone={false}
                                options={APPLICANT_TYPES.map((t) => ({ value: t.value, label: t.label }))}
                                value={values.applicant_type ?? null}
                                onChange={(v) => set("applicant_type", v)}
                            />
                        </Field>
                    </div>
                </section>

                <section className={styles.section} aria-labelledby="group-education">
                    {sectionHead("group-education", "03", "Education", sections.education)}
                    <div className={styles.fields}>
                        <Field {...field("has_degree")} group>
                            <SingleChoice
                                name="has_degree"
                                withNone={false}
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
                                        placeholder="e.g. Fine Art"
                                        value={values.degree_field ?? ""}
                                        onChange={(e) => set("degree_field", e.target.value || null)}
                                        {...ariaFor("degree_field")}
                                    />
                                </Field>

                                <Field {...field("graduation_year")}>{yearInput("graduation_year")}</Field>
                            </>
                        )}

                        <Field {...field("education")} group full>
                            <SchoolsEditor
                                id="field-education"
                                schools={values.education ?? []}
                                countries={options.countries}
                                onChange={(schools) => set("education", schools)}
                                describedBy={ariaFor("education")["aria-describedby"]}
                            />
                        </Field>

                        <Field {...field("currently_enrolled")} group>
                            <SingleChoice
                                name="currently_enrolled"
                                withNone={false}
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

            <div className={onboarding.bar}>
                <div className={onboarding.barInner}>
                    <Link href="/documents" className={`${buttons.secondary} ${onboarding.back}`}>
                        ← Back
                    </Link>
                    <span
                        className={`${onboarding.status} ${styles.status} ${saveState.kind === "error" ? styles.statusError : ""}`}
                        role={saveState.kind === "error" ? "alert" : "status"}
                    >
                        <span className={`${styles.dot} ${marker}`} aria-hidden="true" />
                        <span>{status}</span>
                    </span>
                    {/* everything saved: on to the last step, Projects */}
                    {allSaved ? (
                        <Link href="/projects" className={`${buttons.primary} ${onboarding.next}`}>
                            Continue to Projects →
                        </Link>
                    ) : (
                        <button
                            type="submit"
                            form="profile-form"
                            className={`${buttons.primary} ${onboarding.next}`}
                            disabled={saveState.kind === "saving"}
                        >
                            {saveState.kind === "saving" ? "Saving…" : "Save profile"}
                        </button>
                    )}
                </div>
            </div>
        </main>
    );
};

export default ProfileEditor;
