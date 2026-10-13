import Link from "next/link";
import ClampedText from "@/components/ClampedText/ClampedText";
import Highlighted from "@/components/Highlighted/Highlighted";
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

// Where a requirement row comes from (api/discover.py RequirementOut): the RQ1 eligibility classifier,
// a person's review, or the keyword safety net. Shown small under the reason, so the model's work is
// visible and auditable; a merged row of generic checks has no source and shows none.
const sourceLabel = (requirement: Requirement): string | null => {
    if (!requirement.label || !requirement.found_by) return null;
    if (requirement.found_by === "reviewed") return "checked by hand";
    if (requirement.found_by === "keyword_check") return "flagged by keyword check";
    if (requirement.found_by === "rule") return "found by a rule";
    return requirement.confidence != null
        ? `classifier, ${Math.round(requirement.confidence * 100)}% sure`
        : "classifier";
};

// The call's details as extracted from its page, in display order. Texts are verbatim, in the
// call's own language (not translated); a list shows one row per question or document.
type CallDetail = { title: string; text?: string; items?: string[] };

const callDetails = (call: Opportunity): CallDetail[] => {
    const details: CallDetail[] = [
        { title: "Project requirements", text: call.project_requirements ?? undefined },
        {
            title: "Application questions",
            items: call.application_questions.map((q) => (q.limit ? `${q.question} (${q.limit})` : q.question)),
        },
        { title: "How to apply", text: call.how_to_apply ?? undefined },
        {
            title: "What to send",
            items: call.required_materials.map((m) => (m.details ? `${m.item}: ${m.details}` : m.item)),
        },
        { title: "Selection criteria", text: call.selection_criteria ?? undefined },
        { title: "Application language", text: call.application_language ?? undefined },
        { title: "How to submit", text: call.submission_method ?? undefined },
        { title: "Programme dates", text: call.program_dates ?? undefined },
    ];
    return details.filter((detail) => (detail.items ? detail.items.length > 0 : Boolean(detail.text)));
};

// One call (design: DISCOVER.md → Opportunity): facts and description on the left, "Can you
// apply?" on the right, every eligibility sentence quoted verbatim once, with each requirement it
// states and what that means for the artist (a sentence can state several: "over 18 ... and reside
// in Senegal" -> an age row and a residence row). Rendered on the server; only "Back to results", the
// quotes' "Show more" and the draft placeholder run in the browser.
const OpportunityView = ({ call }: { call: Opportunity }) => {
    const place = placeLabel(call.city, call.countries);
    const facts = [
        { label: "Deadline", value: deadlineFact(call.deadline) },
        { label: "Funding", value: call.funding },
        { label: "Application fee", value: call.fee },
        { label: "Type", value: call.types.join(", ") || "Not stated" },
        { label: "Discipline", value: call.disciplines.join(", ") || "Not stated" },
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

                    {/* why "Matched to you" suggests it (api/discover.py why_matched): the specific words
                        the call shares with the artist's documents, marked in the call's sentence and in
                        the artist's own; or, when it shares none, that it is a broad match. Plain word
                        rules (src/matching/explain.py), no model call; absent without documents */}
                    {call.why && (
                        <section aria-labelledby="why-heading" className={styles.why}>
                            <h2 id="why-heading" className={styles.aboutHeading}>
                                Why it&apos;s suggested to you
                            </h2>
                            {call.why.shared.length > 0 ? (
                                <>
                                    <p className={styles.whyLabel}>In common with your documents</p>
                                    <p className={styles.shared}>
                                        {call.why.shared.map((word) => (
                                            <span key={word} className={styles.sharedWord}>
                                                {word.toLowerCase()}
                                            </span>
                                        ))}
                                    </p>
                                    {call.why.call_sentence && (
                                        <>
                                            <p className={styles.whyLabel}>The call says</p>
                                            <blockquote className={styles.whyQuote}>
                                                “<Highlighted text={call.why.call_sentence} words={call.why.call_highlight} />”
                                            </blockquote>
                                        </>
                                    )}
                                    {call.why.your_sentence && (
                                        <>
                                            <p className={styles.whyLabel}>Your {call.why.your_document} says</p>
                                            <blockquote className={styles.whyQuote}>
                                                “<Highlighted text={call.why.your_sentence} words={call.why.your_highlight} />”
                                            </blockquote>
                                        </>
                                    )}
                                </>
                            ) : (
                                <p className={styles.broad}>
                                    A broad match: the call is close to your documents in general, but names nothing
                                    specific from your practice. Read it to judge whether it fits.
                                </p>
                            )}
                        </section>
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
                                {/* long sentences: a three-line preview, "Show more" for the rest */}
                                <ClampedText as="blockquote" className={styles.quote}>
                                    “{sentence.quote}”
                                </ClampedText>
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
                                                    {sourceLabel(requirement) && (
                                                        <p className={styles.source}>
                                                            <span className={styles.label}>{requirement.label}</span>
                                                            {sourceLabel(requirement)}
                                                        </p>
                                                    )}
                                                </div>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </li>
                        ))}
                    </ul>

                    {/* the call's own details (combined re-extraction), collapsed so they don't compete
                        with the checks; only the ones the call states */}
                    {callDetails(call).map((detail) => (
                        <details key={detail.title} className={styles.extra}>
                            <summary className={styles.extraSummary}>
                                {detail.title}
                                {detail.items && ` · ${detail.items.length}`}
                            </summary>
                            {detail.items ? (
                                <ul className={styles.extraList}>
                                    {detail.items.map((text, i) => (
                                        <li key={i}>{text}</li>
                                    ))}
                                </ul>
                            ) : (
                                <p className={styles.extraText}>{detail.text}</p>
                            )}
                        </details>
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
