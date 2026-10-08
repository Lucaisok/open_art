import { useId, type InputHTMLAttributes } from "react";
import styles from "./TextField.module.css";

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
    label: string;
    hint?: string; // shown under the label and read out by screen readers with the field
};

// A labelled input. The label is always visible: placeholders alone disappear while typing.
const TextField = ({ label, hint, ...inputProps }: TextFieldProps) => {
    const id = useId();
    const hintId = `${id}-hint`;
    return (
        <div className={styles.field}>
            <label htmlFor={id} className={styles.label}>
                {label}
            </label>
            {hint && (
                <p id={hintId} className={styles.hint}>
                    {hint}
                </p>
            )}
            <input id={id} className={styles.input} aria-describedby={hint ? hintId : undefined} {...inputProps} />
        </div>
    );
};

export default TextField;
