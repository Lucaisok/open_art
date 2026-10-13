import Link from "next/link";
import ClampedText from "@/components/ClampedText/ClampedText";
import VerdictBadge from "@/components/VerdictBadge/VerdictBadge";
import { deadlineLabel, placeLabel } from "@/lib/discover";
import type { SearchResult } from "@/lib/types";
import styles from "./ResultCard.module.css";

type ResultCardProps = {
    result: SearchResult;
    onOpen: () => void;           // remembers the scroll position before leaving
};

// One call in the results. The whole card opens the call's page: the title is a link (not the
// prototype's button: it navigates, so it can also be opened in a new tab) stretched over the card,
// so the reason's "Show more" can sit above it without opening the call. A stated deadline and,
// when it is one clear, significant sum (api/discover.py headline_funding), the money stand out in lime.
// a call open to many disciplines lists them all on its page; the card shows the first few
const MAX_DISCIPLINES = 3;

const ResultCard = ({ result, onOpen }: ResultCardProps) => (
    <li className={styles.item}>
        <div className={styles.card}>
            {(result.types.length > 0 || result.disciplines.length > 0) && (
                <span className={styles.types}>
                    {result.types.map((type) => (
                        <span key={type} className={styles.type}>
                            {type}
                        </span>
                    ))}
                    {/* who the call is for, in a quieter chip than the type; at most MAX_DISCIPLINES */}
                    {result.disciplines.slice(0, MAX_DISCIPLINES).map((discipline) => (
                        <span key={discipline} className={styles.discipline}>
                            {discipline}
                        </span>
                    ))}
                    {result.disciplines.length > MAX_DISCIPLINES && (
                        <span className={styles.discipline}>
                            +{result.disciplines.length - MAX_DISCIPLINES}
                            <span className={styles.visuallyHidden}> more disciplines</span>
                        </span>
                    )}
                </span>
            )}
            <Link
                href={`/opportunities/${encodeURIComponent(result.id)}`}
                className={styles.title}
                onClick={onOpen}
            >
                {result.title}
            </Link>
            {result.organisation && <span className={styles.organisation}>{result.organisation}</span>}
            {/* why "Matched to you" ranks it here: the call's own sentence closest to the artist's
                documents (api/discover.py ResultOut.evidence); none when ordered by deadline */}
            {result.evidence && (
                <div className={styles.why}>
                    <span className={styles.whyLabel}>Why it&apos;s here</span>
                    <ClampedText className={styles.whyQuote}>“{result.evidence}”</ClampedText>
                </div>
            )}
            <span className={styles.facts}>
                <span>{placeLabel(result.city, result.countries)}</span>
                <span className={result.deadline ? styles.highlight : undefined}>{deadlineLabel(result.deadline)}</span>
                {result.funding && <span className={styles.highlight}>{result.funding}</span>}
            </span>
            <div className={styles.bottom}>
                <div className={styles.verdict}>
                    <VerdictBadge status={result.status} />
                    <ClampedText className={styles.reason}>{result.reason}</ClampedText>
                </div>
            </div>
        </div>
    </li>
);

export default ResultCard;
