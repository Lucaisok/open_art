import styles from "./ProfileEditor.module.css";

// Native radios and checkboxes styled as pills or a segmented switch. The input is visually
// hidden but still the real control (keyboard, screen readers); its focus shows on the pill.

type Option<T> = { value: T; label: string };

type SingleChoiceProps<T> = {
    name: string;
    options: Option<T>[];
    value: T | null;
    onChange: (value: T | null) => void;
    look?: "pills" | "switch"; // switch: used in the Studio's profile modal
    withNone?: boolean; // a "Not said" option (= null). Without it, choosing the chosen one again clears it.
};

// One answer or none: every profile field is optional
export const SingleChoice = <T extends string | boolean>({
    name,
    options,
    value,
    onChange,
    look = "pills",
    withNone = true,
}: SingleChoiceProps<T>) => {
    const all: Option<T | null>[] = withNone ? [...options, { value: null, label: "Not said" }] : options;
    return (
        <div className={look === "switch" ? styles.switch : styles.pills}>
            {all.map((option) => {
                const checked = option.value === value;
                return (
                    <label key={String(option.value)} className={`${styles.choice} ${checked ? styles.choiceOn : ""}`}>
                        <input
                            type="radio"
                            name={name}
                            className={styles.hiddenInput}
                            checked={checked}
                            onChange={() => onChange(option.value)}
                            // a click (or Space) on the chosen one: no change event, so clear it here
                            onClick={() => {
                                if (checked && option.value !== null) {
                                    onChange(null);
                                }
                            }}
                        />
                        {option.label}
                    </label>
                );
            })}
        </div>
    );
};

type MultiChoiceProps = {
    name: string;
    options: string[];
    values: string[];
    onChange: (values: string[]) => void;
};

// Any number of answers (disciplines)
export const MultiChoice = ({ name, options, values, onChange }: MultiChoiceProps) => (
    <div className={styles.pills}>
        {options.map((option) => {
            const checked = values.includes(option);
            return (
                <label key={option} className={`${styles.choice} ${checked ? styles.choiceOn : ""}`}>
                    <input
                        type="checkbox"
                        name={name}
                        className={styles.hiddenInput}
                        checked={checked}
                        onChange={() =>
                            // keep the list in the options' order
                            onChange(options.filter((o) => (o === option ? !checked : values.includes(o))))
                        }
                    />
                    {option}
                </label>
            );
        })}
    </div>
);
