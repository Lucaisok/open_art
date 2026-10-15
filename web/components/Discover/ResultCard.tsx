import Link from "next/link";
import ClampedText from "@/components/ClampedText/ClampedText";
import SaveCall from "@/components/SaveCall/SaveCall";
import VerdictBadge from "@/components/VerdictBadge/VerdictBadge";
import { deadlineLabel, matchBand, placeLabel } from "@/lib/discover";
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
            {result.types.length > 0 && (
                <span className={styles.types}>
                    {result.types.map((type) => (
                        <span key={type} className={styles.type}>
                            {type}
                        </span>
                    ))}
                </span>
            )}
            <Link
                href={`/opportunities/${encodeURIComponent(result.id)}`}
                className={styles.title}
                title={result.title}   // the whole title on hover, when the card cuts it
                onClick={onOpen}
            >
                {result.title}
            </Link>
            {result.organisation && <span className={styles.organisation}>{result.organisation}</span>}
            {/* who the call is for: grey chips under the organisation; at most MAX_DISCIPLINES */}
            {result.disciplines.length > 0 && (
                <span className={styles.disciplines}>
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
            <span className={styles.facts}>
                <span>{placeLabel(result.city, result.countries)}</span>
                <span className={result.deadline ? styles.highlight : undefined}>{deadlineLabel(result.deadline)}</span>
                {result.funding && <span className={styles.highlight}>{result.funding}</span>}
            </span>
            <div className={styles.bottom}>
                {/* why "Matched to you" ranks it here (api/discover.py CardWhyOut): the specific words it
                    shares with the artist's documents, or, when it shares none, that it is a broad match.
                    The sentences holding the words are on the call page. None when ordered by deadline.
                    Just above the verdict's dividing line, under the facts */}
                {result.why && (
                    <div className={styles.why}>
                        {/* the chance it is a clear fit (src/matching/score.py), shown, never used to rank */}
                        <span className={styles.match}>
                            {matchBand(result.why.match)} · {result.why.match}%
                        </span>
                        {result.why.shared.length > 0 ? (
                            <>
                                <span className={styles.whyLabel}>In common with your documents</span>
                                <span className={styles.shared}>
                                    {result.why.shared.map((word) => (
                                        <span key={word} className={styles.sharedWord}>
                                            {word.toLowerCase()}
                                        </span>
                                    ))}
                                </span>
                            </>
                        ) : (
                            <span className={styles.broad}>
                                Broad match: close to your documents in general, nothing specific in common
                            </span>
                        )}
                    </div>
                )}
                <div className={styles.verdict}>
                    <VerdictBadge status={result.status} />
                    <ClampedText className={styles.reason}>{result.reason}</ClampedText>
                </div>
            </div>
            {/* to the artist's Studio (api/saved.py): top right, above the title's link */}
            <SaveCall id={result.id} title={result.title} initial={result.saved} />
        </div>
    </li>
);

export default ResultCard;
