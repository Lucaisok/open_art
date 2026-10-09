import { VERDICTS } from "@/lib/discover";
import type { VerdictStatus } from "@/lib/types";
import styles from "./VerdictBadge.module.css";

const LOOK: Record<VerdictStatus, string> = {
    ELIGIBLE: styles.eligible,
    CHECK: styles.check,
    LIKELY_NOT_ELIGIBLE: styles.notEligible,
};

// The eligibility verdict as a pill: icon + words + its own fill, never colour alone.
// "large" on the opportunity page, small on the result cards.
const VerdictBadge = ({ status, large = false }: { status: VerdictStatus; large?: boolean }) => (
    <span className={`${styles.badge} ${LOOK[status]} ${large ? styles.large : ""}`}>
        <span aria-hidden="true">{VERDICTS[status].icon}</span>
        <span>{VERDICTS[status].label}</span>
    </span>
);

export default VerdictBadge;
