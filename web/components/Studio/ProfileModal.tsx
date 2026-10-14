"use client";

import { useState } from "react";
import { requestJson } from "@/lib/api";
import { forgetSearch } from "@/lib/discover";
import type { ProfileData, ProfileOptions, ProfileValues } from "@/lib/types";
import Modal from "@/components/ui/Modal";
import buttons from "@/components/ui/buttons.module.css";
import { MultiChoice, SingleChoice } from "@/components/ProfileEditor/Choices";
import CountryChips from "@/components/ProfileEditor/CountryChips";
import DateParts from "@/components/ProfileEditor/DateParts";
import Field, { describedBy } from "@/components/ProfileEditor/Field";
import { HELPERS, startingPoint, toYear } from "@/components/ProfileEditor/ProfileEditor";
import SchoolsEditor from "@/components/ProfileEditor/SchoolsEditor";
import { APPLICANT_TYPES, CAREER_STAGE_LABELS, FIELD_LABELS, formatValue, type FieldName } from "@/components/ProfileEditor/fields";
import editor from "@/components/ProfileEditor/ProfileEditor.module.css";
import styles from "./ProfileModal.module.css";

const TABS = [
    { key: "about", label: "About you", fields: ["name", "birth_date", "nationalities", "residence_country", "residence_city", "languages"] },
    { key: "practice", label: "Your practice", fields: ["disciplines", "career_stage", "active_since", "applicant_type"] },
    { key: "education", label: "Education", fields: ["has_degree", "degree_field", "graduation_year", "education", "currently_enrolled"] },
] as const;
type Tab = (typeof TABS)[number]["key"];

const THIS_YEAR = new Date().getFullYear();

type ProfileModalProps = {
    initial: ProfileData;
    options: ProfileOptions;
    onClose: () => void;
    onSaved: (profile: ProfileData) => void;
};

// Edit profile (design: STUDIO.md → Edit profile): the profile page's fields in three tabs. Values
// read from documents not reviewed yet are filled into the empty fields and marked "From your CV /
// portfolio", with the quote, exactly as on the onboarding's profile page (startingPoint): the same
// controls and the same rules. Only "Save profile" writes anything (PUT /api/profile), which also
// marks those documents as reviewed.
const ProfileModal = ({ initial, options, onClose, onSaved }: ProfileModalProps) => {
    const [start] = useState(() => startingPoint(initial));
    const [values, setValues] = useState<ProfileValues>(start.values);
    const [evidence, setEvidence] = useState(start.evidence);
    const [differing, setDiffering] = useState(start.differing);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [tab, setTab] = useState<Tab>("about");
    const [birthIncomplete, setBirthIncomplete] = useState(false);
    const [busy, setBusy] = useState(false);
    const [problem, setProblem] = useState<string | null>(null);

    // a change by hand: the field's quote and error go
    const set = <K extends FieldName>(name: K, value: ProfileValues[K]) => {
        setValues((prev) => ({ ...prev, [name]: value }));
        setEvidence((prev) => {
            const next = { ...prev };
            delete next[name];
            return next;
        });
        setDiffering((prev) => {
            const next = { ...prev };
            delete next[name];
            return next;
        });
        setErrors((prev) => ({ ...prev, [name]: "" }));
    };
    const field = (name: FieldName) => {
        const fromDocument = differing[name];
        return {
            id: `field-${name}`,
            label: FIELD_LABELS[name],
            helper: HELPERS[name],
            error: errors[name] || undefined,
            evidence: evidence[name],
            cvSays: fromDocument
                ? {
                      value: formatValue(name, fromDocument.value, options) ?? "",
                      quote: fromDocument.quote,
                      source: fromDocument.source,
                      onUse: () => {
                          set(name, fromDocument.value as never);
                          setEvidence((prev) => ({ ...prev, [name]: { quote: fromDocument.quote, citation: fromDocument.citation,
                                                                      source: fromDocument.source } }));
                      },
                  }
                : undefined,
        };
    };
    const aria = (name: FieldName) => ({
        "aria-describedby": describedBy(`field-${name}`, HELPERS[name], errors[name] || undefined),
        "aria-invalid": errors[name] ? true : undefined,
    });

    const save = async () => {
        if (birthIncomplete) {
            setTab("about");
            setErrors((prev) => ({ ...prev, birth_date: "Enter the full date: day, month and year." }));
            return;
        }
        setBusy(true);
        setProblem(null);
        const result = await requestJson<ProfileData>("PUT", "/api/profile", {
            values,
            evidence,
            reviewed_documents: initial.suggestions?.documents.map((d) => d.id) ?? [],
        });
        setBusy(false);
        if (!result.ok) {
            setErrors(result.fieldErrors);
            const first = Object.keys(result.fieldErrors)[0];
            const where = TABS.find((t) => (t.fields as readonly string[]).includes(first));
            if (where) setTab(where.key);
            setProblem(first ? "Fix the field marked in red." : result.error);
            return;
        }
        forgetSearch();   // Discover starts again from the saved profile's disciplines
        onSaved(result.data);
    };

    const errorIn = (t: (typeof TABS)[number]) => t.fields.some((name) => errors[name]);
    return (
        <Modal
            title="Edit profile"
            onClose={onClose}
            busy={busy}
            footer={
                <>
                    {problem && <p role="alert" className={`${buttons.error} ${styles.problem}`}>{problem}</p>}
                    <button type="button" className={buttons.secondary} onClick={onClose} disabled={busy}>Cancel</button>
                    <button type="button" className={buttons.primary} onClick={save} disabled={busy}>
                        {busy ? "Saving…" : "Save profile"}
                    </button>
                </>
            }
        >
            <div role="tablist" aria-label="Profile sections" className={styles.tabs}>
                {TABS.map((t) => (
                    <button key={t.key} type="button" role="tab" id={`tab-${t.key}`} aria-selected={tab === t.key}
                            aria-controls={`panel-${t.key}`} className={styles.tab} onClick={() => setTab(t.key)}>
                        {t.label}
                        {errorIn(t) && <span className={styles.tabError} aria-label="has an error">!</span>}
                    </button>
                ))}
            </div>

            <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className={`${styles.panel} ${editor.inModal}`}>
                {tab === "about" && (
                    <>
                        <Field {...field("name")}>
                            <input id="field-name" type="text" className={editor.input} maxLength={120} autoComplete="name"
                                   placeholder="As you sign your work" value={values.name ?? ""}
                                   onChange={(e) => set("name", e.target.value || null)} {...aria("name")} />
                        </Field>
                        <Field {...field("birth_date")} group>
                            <DateParts id="field-birth_date" value={values.birth_date ?? null}
                                       onChange={(v) => set("birth_date", v)} onIncomplete={setBirthIncomplete}
                                       describedBy={aria("birth_date")["aria-describedby"]} invalid={Boolean(errors.birth_date)} />
                        </Field>
                        <Field {...field("nationalities")}>
                            <CountryChips id="field-nationalities" codes={values.nationalities ?? []} countries={options.countries}
                                          onChange={(codes) => set("nationalities", codes)}
                                          describedBy={aria("nationalities")["aria-describedby"]} />
                        </Field>
                        <div className={styles.pair}>
                            <Field {...field("residence_country")}>
                                <select id="field-residence_country" className={`${editor.input} ${editor.select}`}
                                        value={values.residence_country ?? ""}
                                        onChange={(e) => set("residence_country", e.target.value || null)} {...aria("residence_country")}>
                                    <option value="">Not said</option>
                                    {options.countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                                </select>
                            </Field>
                            <Field {...field("residence_city")}>
                                <input id="field-residence_city" type="text" className={editor.input} maxLength={100}
                                       autoComplete="address-level2" placeholder="e.g. Berlin" value={values.residence_city ?? ""}
                                       onChange={(e) => set("residence_city", e.target.value || null)} {...aria("residence_city")} />
                            </Field>
                        </div>
                        <Field {...field("languages")}>
                            <CountryChips id="field-languages" noun="language" codes={values.languages ?? []}
                                          countries={options.languages} onChange={(codes) => set("languages", codes)}
                                          describedBy={aria("languages")["aria-describedby"]} />
                        </Field>
                    </>
                )}

                {tab === "practice" && (
                    <>
                        <Field {...field("disciplines")} group>
                            <MultiChoice name="disciplines" options={options.disciplines} values={values.disciplines ?? []}
                                         onChange={(list) => set("disciplines", list)} />
                        </Field>
                        <Field {...field("career_stage")} group>
                            <SingleChoice name="career_stage"
                                          options={options.career_stages.map((s) => ({ value: s, label: CAREER_STAGE_LABELS[s] ?? s }))}
                                          value={values.career_stage ?? null} onChange={(v) => set("career_stage", v)} />
                        </Field>
                        <Field {...field("active_since")}>
                            <input id="field-active_since" type="number" inputMode="numeric"
                                   className={`${editor.input} ${editor.inputYear}`} min={1900} max={THIS_YEAR} placeholder="e.g. 2016"
                                   value={values.active_since ?? ""} onChange={(e) => set("active_since", toYear(e.target.value))}
                                   {...aria("active_since")} />
                        </Field>
                        <Field {...field("applicant_type")} group>
                            <SingleChoice name="applicant_type" look="switch"
                                          options={APPLICANT_TYPES.map((t) => ({ value: t.value, label: t.label }))}
                                          value={values.applicant_type ?? null} onChange={(v) => set("applicant_type", v)} />
                        </Field>
                    </>
                )}

                {tab === "education" && (
                    <>
                        <Field {...field("has_degree")} group>
                            <SingleChoice name="has_degree" look="switch"
                                          options={[{ value: true, label: "Yes" }, { value: false, label: "No" }]}
                                          value={values.has_degree ?? null}
                                          onChange={(v) => {
                                              set("has_degree", v);
                                              if (v === false) {
                                                  set("degree_field", null);
                                                  set("graduation_year", null);
                                              }
                                          }} />
                        </Field>
                        {values.has_degree !== false && (
                            <div className={styles.pair}>
                                <Field {...field("degree_field")}>
                                    <input id="field-degree_field" type="text" className={editor.input} maxLength={200}
                                           placeholder="e.g. Painting" value={values.degree_field ?? ""}
                                           onChange={(e) => set("degree_field", e.target.value || null)} {...aria("degree_field")} />
                                </Field>
                                <Field {...field("graduation_year")}>
                                    <input id="field-graduation_year" type="number" inputMode="numeric"
                                           className={`${editor.input} ${editor.inputYear}`} min={1900} max={THIS_YEAR}
                                           placeholder="e.g. 2021" value={values.graduation_year ?? ""}
                                           onChange={(e) => set("graduation_year", toYear(e.target.value))} {...aria("graduation_year")} />
                                </Field>
                            </div>
                        )}
                        <Field {...field("education")} group>
                            <SchoolsEditor id="field-education" schools={values.education ?? []} countries={options.countries}
                                           onChange={(schools) => set("education", schools)}
                                           describedBy={aria("education")["aria-describedby"]} />
                        </Field>
                        <Field {...field("currently_enrolled")} group>
                            <SingleChoice name="currently_enrolled" look="switch"
                                          options={[{ value: true, label: "Yes" }, { value: false, label: "No" }]}
                                          value={values.currently_enrolled ?? null} onChange={(v) => set("currently_enrolled", v)} />
                        </Field>
                    </>
                )}
            </div>
        </Modal>
    );
};

export default ProfileModal;
