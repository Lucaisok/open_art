import Link from "next/link";
import VerdictBadge from "@/components/VerdictBadge/VerdictBadge";
import { deadlineFact, placeLabel } from "@/lib/discover";
import type { Opportunity } from "@/lib/types";
import BackToResults from "./BackToResults";
import DraftButton from "./DraftButton";
import styles from "./OpportunityView.module.css";

type Sentence = Opportunity["verdict"]["sentences"][number];
type Requirement = Sentence["requirements"][number];

// What each outcome looks like (design: DISCOVER.md → "Can you apply?"). Icon + words for every
// outcome, never colour alone. Listed in display order: failures (only if any), then passes, then
// checks; the API sorts the sentences and their rows the same way.
const OUTCOMES: Record<Requirement["outcome"], { count: "fails" | "checks" | "passes"; title: string; icon: string; look: string }> = {
    FAIL: { count: "fails", title: "Doesn't pass", icon: "✕", look: styles.iconFail },
    PASS: { count: "passes", title: "Passes", icon: "✓", look: styles.iconPass },
    CHECK: { count: "checks", title: "To check", icon: "○", look: styles.iconCheck },
};

// One call (design: DISCOVER.md → Opportunity): facts and description on the left, "Can you
// apply?" on the right, every eligibility sentence quoted verbatim once, with each requirement it
// states and what that means for the artist (a sentence can state several: "over 18 ... and reside
// in Senegal" -> an age row and a residence row). Rendered on the server; only "Back to results" and the draft placeholder run in the browser.
const OpportunityView = ({ call }: { call: Opportunity }) => {
    const place = placeLabel(call.city, call.countries);
    const facts = [
        { label: "Deadline", value: deadlineFact(call.deadline) },
        { label: "Funding", value: call.funding },
        { label: "Application fee", value: call.fee },
        { label: "Type", value: call.types.join(", ") || "Not stated" },
        { label: "Place", value: place },
    ];

    return (
        <main id="main" className={styles.main}>
            <BackToResults />

            {call.types.length > 0 && (
                <div className={styles.types}>
                    {call.types.map((type) => (
                        <span key={type} className={styles.type}>
                            {type}
                        </span>
                    ))}
                </div>
            )}
            <h1 className={styles.title}>{call.title}</h1>
            <p className={styles.byline}>{[call.organisation, place].filter(Boolean).join(" · ")}</p>

            <div className={styles.columns}>
                <div className={styles.facts}>
                    <dl className={styles.factList}>
                        {facts.map((fact) => (
                            <div key={fact.label} className={styles.fact}>
                                <dt className={styles.factLabel}>{fact.label}</dt>
                                <dd className={styles.factValue}>{fact.value}</dd>
                            </div>
                        ))}
                    </dl>

                    {call.description && (
                        <>
                            <h2 className={styles.aboutHeading}>About this call</h2>
                            <p className={styles.description}>{call.description}</p>
                        </>
                    )}

                    <a href={call.source_url} target="_blank" rel="noopener noreferrer" className={styles.original}>
                        Read the original call →<span className={styles.visuallyHidden}> (opens in a new tab)</span>
                    </a>
                </div>

                <section aria-labelledby="apply-heading" className={styles.apply}>
                    <h2 id="apply-heading" className={styles.applyTitle}>
                        Can you apply?
                    </h2>
                    <div className={styles.verdict}>
                        <VerdictBadge status={call.verdict.status} large />
                        {/* "Likely not eligible: <quote> (<reason>)" only repeats the badge and the ✕ row
                            below; the other summaries add something (how many checks, no rules found) */}
                        {call.verdict.status !== "LIKELY_NOT_ELIGIBLE" && (
                            <p className={styles.summary}>{call.verdict.summary}</p>
                        )}
                    </div>

                    <ul className={styles.tally} aria-label="Requirements found">
                        {Object.values(OUTCOMES)
                            .filter((outcome) => call.verdict[outcome.count] > 0)
                            .map((outcome) => (
                                <li key={outcome.count} className={styles.tallyItem}>
                                    <span aria-hidden="true" className={`${styles.groupIcon} ${outcome.look}`}>
                                        {outcome.icon}
                                    </span>
                                    <span>
                                        {outcome.title} · {call.verdict[outcome.count]}
                                    </span>
                                </li>
                            ))}
                    </ul>

                    <ul className={styles.checks}>
                        {call.verdict.sentences.map((sentence: Sentence, i: number) => (
                            <li key={i} className={styles.check}>
                                <blockquote className={styles.quote}>“{sentence.quote}”</blockquote>
                                <ul className={styles.requirements}>
                                    {sentence.requirements.map((requirement: Requirement, j: number) => {
                                        const outcome = OUTCOMES[requirement.outcome];
                                        return (
                                            <li key={j} className={styles.requirement}>
                                                <span aria-hidden="true" className={`${styles.groupIcon} ${outcome.look}`}>
                                                    {outcome.icon}
                                                </span>
                                                <div>
                                                    <p className={styles.requirementTitle}>
                                                        {requirement.topic}
                                                        <span className={styles.visuallyHidden}>: {outcome.title}</span>
                                                    </p>
                                                    <p className={styles.reason}>{requirement.reason}</p>
                                                </div>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </li>
                        ))}
                    </ul>

                    {/* sentences that aren't about who can apply: listed apart, never a check (scope) */}
                    {call.verdict.commitments.length > 0 && (
                        <details className={styles.extra}>
                            <summary className={styles.extraSummary}>
                                What you&apos;d commit to · {call.verdict.commitments.length}
                            </summary>
                            <ul className={styles.extraList}>
                                {call.verdict.commitments.map((text: string, i: number) => (
                                    <li key={i}>“{text}”</li>
                                ))}
                            </ul>
                        </details>
                    )}
                    {call.verdict.about_project.length > 0 && (
                        <details className={styles.extra}>
                            <summary className={styles.extraSummary}>
                                About the project · {call.verdict.about_project.length}
                            </summary>
                            <ul className={styles.extraList}>
                                {call.verdict.about_project.map((text: string, i: number) => (
                                    <li key={i}>“{text}”</li>
                                ))}
                            </ul>
                        </details>
                    )}

                    <p className={styles.note}>
                        These checks use your saved profile and the call&apos;s own words. Always read the original
                        call before applying.
                        {!call.profile_filled && (
                            <>
                                {" "}
                                <Link href="/profile" className={styles.noteLink}>
                                    Your profile is empty: fill it in for clearer answers →
                                </Link>
                            </>
                        )}
                    </p>

                    <DraftButton />
                </section>
            </div>
        </main>
    );
};

export default OpportunityView;
