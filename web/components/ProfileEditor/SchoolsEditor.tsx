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
// in a country or region). One row per school (design: OpenArt Profile prototype): its name, city
// and country, each optional except the name, and × to remove it; "+ Add a school" below.
// The boxes are labelled for screen readers; the placeholders say what goes where.
const SchoolsEditor = ({ id, schools, countries, onChange, describedBy }: SchoolsEditorProps) => {
    const update = (index: number, change: Partial<School>) =>
        onChange(schools.map((school, i) => (i === index ? { ...school, ...change } : school)));

    return (
        <div className={styles.schools} aria-describedby={describedBy}>
            {schools.length > 0 && (
                <ul className={styles.schoolList}>
                    {schools.map((school, i) => (
                        <li key={i} className={styles.school}>
                            <label className={styles.srOnly} htmlFor={`${id}-${i}-institution`}>
                                School {i + 1}
                            </label>
                            <input
                                id={`${id}-${i}-institution`}
                                type="text"
                                className={`${styles.input} ${styles.schoolName}`}
                                maxLength={200}
                                placeholder="School"
                                value={school.institution}
                                onChange={(e) => update(i, { institution: e.target.value })}
                            />
                            <label className={styles.srOnly} htmlFor={`${id}-${i}-city`}>
                                City of school {i + 1}
                            </label>
                            <input
                                id={`${id}-${i}-city`}
                                type="text"
                                className={`${styles.input} ${styles.schoolCity}`}
                                maxLength={100}
                                placeholder="City"
                                value={school.city ?? ""}
                                onChange={(e) => update(i, { city: e.target.value || null })}
                            />
                            <label className={styles.srOnly} htmlFor={`${id}-${i}-country`}>
                                Country of school {i + 1}
                            </label>
                            <select
                                id={`${id}-${i}-country`}
                                className={`${styles.input} ${styles.select} ${styles.schoolCountry}`}
                                value={school.country ?? ""}
                                onChange={(e) => update(i, { country: e.target.value || null })}
                            >
                                <option value="">Country</option>
                                {countries.map((c) => (
                                    <option key={c.code} value={c.code}>
                                        {c.name}
                                    </option>
                                ))}
                            </select>
                            <button
                                type="button"
                                className={styles.iconButton}
                                onClick={() => onChange(schools.filter((_, j) => j !== i))}
                                aria-label={`Remove ${school.institution || `school ${i + 1}`}`}
                            >
                                ×
                            </button>
                        </li>
                    ))}
                </ul>
            )}
            <button
                id={id}
                type="button"
                className={styles.textButton}
                onClick={() => onChange([...schools, { institution: "", city: null, country: null }])}
            >
                {schools.length ? "+ Add another school" : "+ Add a school"}
            </button>
        </div>
    );
};

export default SchoolsEditor;
