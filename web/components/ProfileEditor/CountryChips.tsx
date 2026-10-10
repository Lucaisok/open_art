"use client";

import { useState, type KeyboardEvent } from "react";
import type { ProfileOptions } from "@/lib/types";
import styles from "./ProfileEditor.module.css";

type CountryChipsProps = {
    id: string;
    codes: string[];
    countries: ProfileOptions["countries"];
    onChange: (codes: string[]) => void;
    describedBy?: string;
    noun?: string;          // what is picked, in the messages: "country" (default) or "language"
};

// Several countries (nationalities) or languages: removable chips, and a text field with the
// names as suggestions (<datalist>) plus an Add button. Enter in the field adds too.
const CountryChips = ({ id, codes, countries, onChange, describedBy, noun = "country" }: CountryChipsProps) => {
    const [text, setText] = useState("");
    const [problem, setProblem] = useState<string | null>(null);
    const nameOf = (code: string) => countries.find((c) => c.code === code)?.name ?? code;

    const add = () => {
        const typed = text.trim().toLowerCase();
        if (!typed) {
            return;
        }
        const match = countries.find((c) => c.name.toLowerCase() === typed || c.code.toLowerCase() === typed);
        if (!match) {
            setProblem(`Pick a ${noun} from the suggestions.`);
            return;
        }
        if (!codes.includes(match.code)) {
            onChange([...codes, match.code]);
        }
        setText("");
        setProblem(null);
    };

    const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
            event.preventDefault(); // add it, don't submit the form
            add();
        }
    };

    return (
        <div className={styles.chipsBox}>
            {codes.length > 0 && (
                <ul className={styles.chips} aria-label="Added">
                    {codes.map((code) => (
                        <li key={code} className={styles.chip}>
                            {nameOf(code)}
                            <button
                                type="button"
                                className={styles.chipRemove}
                                onClick={() => onChange(codes.filter((c) => c !== code))}
                                aria-label={`Remove ${nameOf(code)}`}
                            >
                                ×
                            </button>
                        </li>
                    ))}
                </ul>
            )}
            <div className={styles.addRow}>
                <input
                    id={id}
                    type="text"
                    list={`${id}-list`}
                    className={styles.input}
                    placeholder={codes.length ? `Add another ${noun}` : `Start typing a ${noun}`}
                    value={text}
                    onChange={(event) => {
                        setText(event.target.value);
                        setProblem(null);
                    }}
                    onKeyDown={onKeyDown}
                    autoComplete="off"
                    aria-describedby={[describedBy, problem ? `${id}-problem` : null].filter(Boolean).join(" ") || undefined}
                />
                <button type="button" className={styles.secondaryButton} onClick={add}>
                    Add
                </button>
            </div>
            <datalist id={`${id}-list`}>
                {countries.map((c) => (
                    <option key={c.code} value={c.name} />
                ))}
            </datalist>
            {problem && (
                <p id={`${id}-problem`} className={styles.fieldError}>
                    {problem}
                </p>
            )}
        </div>
    );
};

export default CountryChips;
