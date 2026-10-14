"use client";

import { useState } from "react";
import styles from "./ProfileEditor.module.css";

type Parts = { day: string; month: string; year: string }; // digits as typed, "" when empty

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
    return { day, month, year }; // "12", "03", "1994"
};

// "12", "3", "1994" -> "1994-03-12", or null if that day doesn't exist (31 February)
const toIso = ({ day, month, year }: Parts): string | null => {
    const d = Number(day);
    const m = Number(month);
    const y = Number(year);
    if (!/^\d{1,2}$/.test(day) || !/^\d{1,2}$/.test(month) || !/^\d{4}$/.test(year)) {
        return null;
    }
    const date = new Date(Date.UTC(y, m - 1, d));
    if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) {
        return null;
    }
    return `${year}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
};

// A date as three boxes: DD, MM, YYYY (design: OpenArt Profile prototype). For a birth date this
// is easier than a calendar, where reaching 1994 means paging back decades. Each box has its own
// label for screen readers; the caller wraps them in a <fieldset> whose legend names the whole date.
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

    const box = (part: keyof Parts, boxId: string, label: string, placeholder: string, autoComplete: string) => (
        <div className={styles.datePart}>
            <label htmlFor={boxId} className={styles.srOnly}>
                {label}
            </label>
            <input
                id={boxId}
                type="text"
                inputMode="numeric"
                autoComplete={autoComplete}
                maxLength={placeholder.length}
                placeholder={placeholder}
                className={styles.input}
                value={parts[part]}
                onChange={(e) => update({ [part]: e.target.value.replace(/\D/g, "") } as Partial<Parts>)}
                {...common}
            />
        </div>
    );

    return (
        <div className={styles.dateParts}>
            {box("day", id, "Day", "DD", "bday-day")}
            {box("month", `${id}-month`, "Month", "MM", "bday-month")}
            {box("year", `${id}-year`, "Year", "YYYY", "bday-year")}
        </div>
    );
};

export default DateParts;
