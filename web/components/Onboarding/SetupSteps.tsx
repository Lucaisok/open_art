import styles from "./Onboarding.module.css";

const STEPS = ["Documents", "Profile", "Projects"];

// The three onboarding steps at the top of each onboarding page: done ones ticked, the current
// one lime, the later ones faded. `current` is 0, 1 or 2.
const SetupSteps = ({ current }: { current: number }) => (
    <ol aria-label="Setup steps" className={styles.steps}>
        {STEPS.map((label, i) => (
            <li
                key={label}
                className={`${styles.step} ${i === current ? styles.stepCurrent : ""} ${i > current ? styles.stepLater : ""}`}
                aria-current={i === current ? "step" : undefined}
            >
                <span className={`${styles.mark} ${i < current ? styles.markDone : i === current ? styles.markNow : ""}`} aria-hidden="true">
                    {i < current ? "✓" : i + 1}
                </span>
                <span className={styles.stepLabel}>{label}</span>
            </li>
        ))}
    </ol>
);

export default SetupSteps;
