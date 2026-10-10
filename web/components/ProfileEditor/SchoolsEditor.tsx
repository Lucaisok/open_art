"use client";

import type { ProfileOptions, ProfileValues } from "@/lib/types";
import styles from "./ProfileEditor.module.css";

type School = ProfileValues["education"][number];

type SchoolsEditorProps = {
    id: string;
    schools: School[];
    countries: ProfileOptions["countries"];
    onChange: (schools: School[]) => void;
    describedBy?: string;
};

// The schools the artist studied at (some calls are for alumni of a school, or for people who studied
// in a country or region). One card per school: its name, city and country, each optional except the
// name, and a Remove button; "Add a school" below. Native inputs only.
const SchoolsEditor = ({ id, schools, countries, onChange, describedBy }: SchoolsEditorProps) => {
    const update = (index: number, change: Partial<School>) =>
        onChange(schools.map((school, i) => (i === index ? { ...school, ...change } : school)));

    return (
        <div className={styles.schools} aria-describedby={describedBy}>
            {schools.length > 0 && (
                <ul className={styles.schoolList}>
                    {schools.map((school, i) => (
                        <li key={i} className={styles.school}>
                            <label className={styles.schoolLabel} htmlFor={`${id}-${i}-institution`}>
                                School
                            </label>
                            <input
                                id={`${id}-${i}-institution`}
                                type="text"
                                className={styles.input}
                                maxLength={200}
                                placeholder="e.g. Academy of Fine Arts Vienna"
                                value={school.institution}
                                onChange={(e) => update(i, { institution: e.target.value })}
                            />
                            <div className={styles.schoolPlace}>
                                <div>
                                    <label className={styles.schoolLabel} htmlFor={`${id}-${i}-city`}>
                                        City
                                    </label>
                                    <input
                                        id={`${id}-${i}-city`}
                                        type="text"
                                        className={styles.input}
                                        maxLength={100}
                                        value={school.city ?? ""}
                                        onChange={(e) => update(i, { city: e.target.value || null })}
                                    />
                                </div>
                                <div>
                                    <label className={styles.schoolLabel} htmlFor={`${id}-${i}-country`}>
                                        Country
                                    </label>
                                    <select
                                        id={`${id}-${i}-country`}
                                        className={`${styles.input} ${styles.select}`}
                                        value={school.country ?? ""}
                                        onChange={(e) => update(i, { country: e.target.value || null })}
                                    >
                                        <option value="">Not given</option>
                                        {countries.map((c) => (
                                            <option key={c.code} value={c.code}>
                                                {c.name}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                            <button
                                type="button"
                                className={styles.textButton}
                                onClick={() => onChange(schools.filter((_, j) => j !== i))}
                                aria-label={`Remove ${school.institution || "this school"}`}
                            >
                                Remove
                            </button>
                        </li>
                    ))}
                </ul>
            )}
            <button
                id={id}
                type="button"
                className={styles.secondaryButton}
                onClick={() => onChange([...schools, { institution: "", city: null, country: null }])}
            >
                {schools.length ? "Add another school" : "Add a school"}
            </button>
        </div>
    );
};

export default SchoolsEditor;
