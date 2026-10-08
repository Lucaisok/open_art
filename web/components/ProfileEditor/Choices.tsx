import styles from "./ProfileEditor.module.css";

// Native radios and checkboxes styled as pills or a segmented switch. The input is visually
// hidden but still the real control (keyboard, screen readers); its focus shows on the pill.

type Option<T> = { value: T; label: string };

type SingleChoiceProps<T> = {
    name: string;
    options: Option<T>[];
    value: T | null;
    onChange: (value: T | null) => void;
    look?: "pills" | "switch"; // switch: the Auth page's mode switch, for Yes / No / Not said
};

// One answer, plus "Not said" (= null): every profile field is optional
export const SingleChoice = <T extends string | boolean>({
    name,
    options,
    value,
    onChange,
    look = "pills",
}: SingleChoiceProps<T>) => {
    const all: Option<T | null>[] = [...options, { value: null, label: "Not said" }];
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
