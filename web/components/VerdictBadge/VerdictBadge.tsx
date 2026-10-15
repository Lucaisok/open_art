import { VERDICTS } from "@/lib/discover";
import type { VerdictStatus } from "@/lib/types";
import styles from "./VerdictBadge.module.css";

const LOOK: Record<VerdictStatus, string> = {
    ELIGIBLE: styles.eligible,
    CHECK: styles.check,
    LIKELY_NOT_ELIGIBLE: styles.notEligible,
};

// The eligibility verdict: a dot + words, never colour alone (lime dot, hollow ring, ink dot).
// "large" on the opportunity page, small on the result cards.
const VerdictBadge = ({ status, large = false }: { status: VerdictStatus; large?: boolean }) => (
    <span className={`${styles.badge} ${LOOK[status]} ${large ? styles.large : ""}`}>
        <span aria-hidden="true" className={styles.dot} />
        <span>{VERDICTS[status].label}</span>
    </span>
);

export default VerdictBadge;
