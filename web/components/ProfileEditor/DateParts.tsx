"use client";

import { useState } from "react";
import styles from "./ProfileEditor.module.css";

const MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];

type Parts = { day: string; month: string; year: string }; // month: "1".."12" or ""

type DatePartsProps = {
    id: string; // given to the Day box, so an error can move focus there
    value: string | null; // "1994-03-12" or null
    onChange: (value: string | null) => void; // a full, real date, or null when all three are empty
    onIncomplete: (incomplete: boolean) => void; // some boxes filled, or not a real date: Save is blocked
    // (the editor resets it to false whenever it sets the date itself)
    describedBy?: string;
    invalid?: boolean;
};

const fromIso = (value: string | null): Parts => {
    if (!value) {
        return { day: "", month: "", year: "" };
    }
    const [year, month, day] = value.split("-");
    return { day: String(Number(day)), month: String(Number(month)), year };
};

// "12", "3", "1994" -> "1994-03-12", or null if that day doesn't exist (31 February)
const toIso = ({ day, month, year }: Parts): string | null => {
    const d = Number(day);
    const m = Number(month);
    const y = Number(year);
    if (!/^\d{1,2}$/.test(day) || !/^\d{4}$/.test(year) || !m) {
        return null;
    }
    const date = new Date(Date.UTC(y, m - 1, d));
    if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) {
        return null;
    }
    return `${year}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
};

// A date as three boxes: Day, Month (a list), Year. For a birth date this is easier than a
// calendar, where reaching 1994 means paging back decades. Each box has its own visible label;
// the caller wraps them in a <fieldset> whose legend names the whole date.
const DateParts = ({ id, value, onChange, onIncomplete, describedBy, invalid }: DatePartsProps) => {
    const [parts, setParts] = useState<Parts>(() => fromIso(value));
    const [shown, setShown] = useState(value); // the value the boxes were last filled from

    // a value set from outside ("Use this", the saved profile) shows in the boxes. Adjusted during
    // render, React's pattern for state that follows a prop; the editor clears "incomplete" itself.
    if (value !== shown) {
        setShown(value);
        if (value !== toIso(parts)) {
            setParts(fromIso(value));
        }
    }

    const update = (change: Partial<Parts>) => {
        const next = { ...parts, ...change };
        setParts(next);
        const empty = !next.day && !next.month && !next.year;
        const iso = toIso(next);
        if (empty) {
            onIncomplete(false);
            onChange(null);
        } else if (iso) {
            onIncomplete(false);
            if (iso !== value) {
                onChange(iso);
            }
        } else {
            onIncomplete(true); // keep what was typed; Save will ask for the full date
        }
    };

    const common = { "aria-describedby": describedBy, "aria-invalid": invalid || undefined };

    return (
        <div className={styles.dateParts}>
            <div className={styles.datePart}>
                <label htmlFor={id} className={styles.datePartLabel}>
                    Day
                </label>
                <input
                    id={id}
                    type="text"
                    inputMode="numeric"
                    autoComplete="bday-day"
                    maxLength={2}
                    className={`${styles.input} ${styles.inputDay}`}
                    value={parts.day}
                    onChange={(e) => update({ day: e.target.value.replace(/\D/g, "") })}
                    {...common}
                />
            </div>
            <div className={styles.datePart}>
                <label htmlFor={`${id}-month`} className={styles.datePartLabel}>
                    Month
                </label>
                <select
                    id={`${id}-month`}
                    autoComplete="bday-month"
                    className={`${styles.input} ${styles.select} ${styles.inputMonth}`}
                    value={parts.month}
                    onChange={(e) => update({ month: e.target.value })}
                    {...common}
                >
                    {/* empty = not chosen yet; the label above already says "Month" */}
                    <option value="" />
                    {MONTHS.map((name, i) => (
                        <option key={name} value={String(i + 1)}>
                            {name}
                        </option>
                    ))}
                </select>
            </div>
            <div className={styles.datePart}>
                <label htmlFor={`${id}-year`} className={styles.datePartLabel}>
                    Year
                </label>
                <input
                    id={`${id}-year`}
                    type="text"
                    inputMode="numeric"
                    autoComplete="bday-year"
                    maxLength={4}
                    className={`${styles.input} ${styles.inputYear4}`}
                    value={parts.year}
                    onChange={(e) => update({ year: e.target.value.replace(/\D/g, "") })}
                    {...common}
                />
            </div>
        </div>
    );
};

export default DateParts;
