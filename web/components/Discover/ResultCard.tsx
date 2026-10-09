import Link from "next/link";
import VerdictBadge from "@/components/VerdictBadge/VerdictBadge";
import { deadlineLabel, placeLabel } from "@/lib/discover";
import type { SearchResult } from "@/lib/types";
import styles from "./ResultCard.module.css";

type ResultCardProps = {
    result: SearchResult;
    highlightDeadline: boolean;   // "All calls" is ordered by deadline, so the deadline stands out
    onOpen: () => void;           // remembers the scroll position before leaving
};

// One call in the results. The whole card is a link to the call's page (a link, not the
// prototype's button: it navigates, so it can also be opened in a new tab).
const ResultCard = ({ result, highlightDeadline, onOpen }: ResultCardProps) => (
    <li className={styles.item}>
        <Link href={`/opportunities/${encodeURIComponent(result.id)}`} className={styles.card} onClick={onOpen}>
            {result.types.length > 0 && (
                <span className={styles.types}>
                    {result.types.map((type) => (
                        <span key={type} className={styles.type}>
                            {type}
                        </span>
                    ))}
                </span>
            )}
            <span className={styles.title}>{result.title}</span>
            {result.organisation && <span className={styles.organisation}>{result.organisation}</span>}
            <span className={styles.facts}>
                <span>{placeLabel(result.city, result.countries)}</span>
                <span className={highlightDeadline ? styles.deadlineHighlight : undefined}>
                    {deadlineLabel(result.deadline)}
                </span>
            </span>
            <span className={styles.bottom}>
                <span className={styles.verdict}>
                    <VerdictBadge status={result.status} />
                    <span className={styles.reason}>{result.reason}</span>
                </span>
            </span>
        </Link>
    </li>
);

export default ResultCard;
