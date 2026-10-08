import styles from "./FormMessage.module.css";

type FormMessageProps = {
    error?: string | null;
    success?: string | null;
};

// The result of a form, announced by screen readers as soon as it appears:
// role="alert" for errors (interrupts), role="status" for confirmations (waits its turn).
const FormMessage = ({ error, success }: FormMessageProps) => {
    if (error) {
        return (
            <p role="alert" className={`${styles.message} ${styles.error}`}>
                {error}
            </p>
        );
    }
    if (success) {
        return (
            <p role="status" className={`${styles.message} ${styles.success}`}>
                {success}
            </p>
        );
    }
    return null;
};

export default FormMessage;
