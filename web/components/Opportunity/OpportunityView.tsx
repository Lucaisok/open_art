import Link from "next/link";
import VerdictBadge from "@/components/VerdictBadge/VerdictBadge";
import { deadlineFact, placeLabel } from "@/lib/discover";
import type { Opportunity } from "@/lib/types";
import BackToResults from "./BackToResults";
import DraftButton from "./DraftButton";
import styles from "./OpportunityView.module.css";

type Check = Opportunity["verdict"]["checks"][number];

// The verdict's sentences, worst first, each group only if it has any (design: DISCOVER.md →
// "Can you apply?"). Icon + words for every group, never colour alone.
const GROUPS: { key: "fails" | "checks" | "passes"; title: string; icon: string; look: string }[] = [
    { key: "fails", title: "Doesn't pass", icon: "✕", look: styles.iconFail },
    { key: "checks", title: "To check", icon: "○", look: styles.iconCheck },
    { key: "passes", title: "Passes", icon: "✓", look: styles.iconPass },
];

// One call (design: DISCOVER.md → Opportunity): facts and description on the left, "Can you
// apply?" on the right, every eligibility sentence quoted verbatim with what it means for the
// artist. Rendered on the server; only "Back to results" and the draft placeholder run in the browser.
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
                        <p className={styles.summary}>{call.verdict.summary}</p>
                    </div>

                    {GROUPS.filter((group) => call.verdict[group.key].length > 0).map((group) => (
                        <div key={group.key} className={styles.group}>
                            <h3 className={styles.groupTitle}>
                                <span aria-hidden="true" className={`${styles.groupIcon} ${group.look}`}>
                                    {group.icon}
                                </span>
                                <span>
                                    {group.title} · {call.verdict[group.key].length}
                                </span>
                            </h3>
                            <ul className={styles.checks}>
                                {call.verdict[group.key].map((check: Check, i: number) => (
                                    <li key={i} className={styles.check}>
                                        <blockquote className={styles.quote}>“{check.quote}”</blockquote>
                                        <p className={styles.reason}>
                                            <span aria-hidden="true">→</span>
                                            <span>{check.reason}</span>
                                        </p>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}

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
