"use client";

import { useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
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

// Several countries (nationalities) or languages (design: OpenArt Profile prototype): removable
// chips and a text field in one underlined box, with the names as suggestions (<datalist>).
// A name is added when picked from the suggestions, on Enter, or when leaving the field with a
// full name typed. Backspace in the empty field removes the last chip.
const CountryChips = ({ id, codes, countries, onChange, describedBy, noun = "country" }: CountryChipsProps) => {
    const [text, setText] = useState("");
    const [problem, setProblem] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const nameOf = (code: string) => countries.find((c) => c.code === code)?.name ?? code;
    const find = (typed: string) => {
        const t = typed.trim().toLowerCase();
        return countries.find((c) => c.name.toLowerCase() === t || c.code.toLowerCase() === t);
    };

    // adds the typed name; `quiet`: say nothing when it isn't one (leaving the field half-typed)
    const add = (typed: string, quiet = false) => {
        if (!typed.trim()) {
            return;
        }
        const match = find(typed);
        if (!match) {
            if (!quiet) {
                setProblem(`Pick a ${noun} from the suggestions.`);
            }
            return;
        }
        if (!codes.includes(match.code)) {
            onChange([...codes, match.code]);
        }
        setText("");
        setProblem(null);
    };

    const onType = (event: ChangeEvent<HTMLInputElement>) => {
        const value = event.target.value;
        setProblem(null);
        // picked from the suggestions (not typed letter by letter): add it at once
        const inputType = (event.nativeEvent as InputEvent).inputType ?? "";
        if (inputType !== "insertText" && !inputType.startsWith("delete") && find(value)) {
            add(value);
            return;
        }
        setText(value);
    };

    const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
            event.preventDefault(); // add it, don't submit the form
            add(text);
        } else if (event.key === "Backspace" && text === "" && codes.length > 0) {
            onChange(codes.slice(0, -1));
        }
    };

    return (
        <div className={styles.chipsBox}>
            {/* a click anywhere in the box goes to the text field */}
            <div className={styles.chipsField} onClick={() => inputRef.current?.focus()}>
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
                <input
                    ref={inputRef}
                    id={id}
                    type="text"
                    list={`${id}-list`}
                    className={styles.chipsInput}
                    placeholder={codes.length ? "Add another" : `Type a ${noun}`}
                    value={text}
                    onChange={onType}
                    onKeyDown={onKeyDown}
                    onBlur={() => add(text, true)}
                    autoComplete="off"
                    aria-describedby={[describedBy, problem ? `${id}-problem` : null].filter(Boolean).join(" ") || undefined}
                />
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
