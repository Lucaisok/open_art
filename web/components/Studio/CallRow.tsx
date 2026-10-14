import Link from "next/link";
import { daysUntil, placeLabel } from "@/lib/discover";
import type { SavedCall } from "@/lib/types";
import buttons from "@/components/ui/buttons.module.css";
import styles from "./Studio.module.css";

// the eligibility marker: never colour alone, the words are next to it
const FIT: Record<string, { label: string; marker: string }> = {
    ELIGIBLE: { label: "Eligible", marker: styles.markerOk },
    CHECK: { label: "To check", marker: styles.markerCheck },
    LIKELY_NOT_ELIGIBLE: { label: "Likely not eligible", marker: styles.markerNo },
};
const WAS: Record<string, string> = { saved: "saved", draft: "in draft", completed: "completed" };

const shortDate = (iso: string, withYear: boolean) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
        day: "numeric", month: "short", timeZone: "UTC", ...(withYear ? { year: "numeric" } : {}),
    });

const dueIn = (days: number) => (days <= 0 ? "today" : days === 1 ? "tomorrow" : `in ${days} days`);

type CallRowProps = {
    call: SavedCall;
    onRemove: (call: SavedCall) => void;
};

// One saved call in the Studio (design: STUDIO.md → My calls): "Type · Place", the title (to the
// call's page), "Organisation · Funding", progress once an application is started; on the right Due
// (red under 7 days) and Fit (marker, verdict, match); then the actions of its stage.
const CallRow = ({ call, onRemove }: CallRowProps) => {
    const closed = call.stage === "closed";
    const days = call.deadline ? daysUntil(call.deadline) : null;
    const urgent = !closed && days !== null && days < 7;
    const apply = `/opportunities/${encodeURIComponent(call.id)}/apply`;
    const fit = call.status ? FIT[call.status] : null;
    const progress = call.progress && call.stage !== "saved"
        ? [["Texts", call.progress.texts_reviewed, call.progress.texts], ["Items", call.progress.items_gathered, call.progress.items]]
              .filter(([, , total]) => Number(total) > 0) as [string, number, number][]
        : [];
    const organisation = [call.organisation, call.funding].filter(Boolean).join(" · ");
    return (
        <li className={`${styles.call} ${closed ? styles.callClosed : ""}`}>
            <div className={styles.callMain}>
                <span className={styles.kicker}>
                    {[call.types[0] ?? "Call", call.listed ? placeLabel(call.city, call.countries) : null].filter(Boolean).join(" · ")}
                </span>
                <h3 className={styles.callTitle}>
                    {call.listed ? <Link href={`/opportunities/${encodeURIComponent(call.id)}`}>{call.title}</Link> : call.title}
                </h3>
                {organisation && <span className={styles.callOrg}>{organisation}</span>}
                {progress.length > 0 && (
                    <span className={styles.progress}>
                        {progress.map(([label, done, total]) => (
                            <span key={label} className={styles.progressItem}>
                                <span>{label} {done} of {total}</span>
                                <span className={styles.progressTrack} aria-hidden="true">
                                    <span className={styles.progressBar} style={{ width: `${Math.round((done / total) * 100)}%` }} />
                                </span>
                            </span>
                        ))}
                    </span>
                )}
            </div>
            <dl className={styles.facts}>
                <dt className={styles.factLabel}>Due</dt>
                <dd className={styles.factValue}>
                    <span className={`${styles.due} ${urgent ? styles.urgent : ""} ${closed ? styles.dueClosed : ""}`}>
                        {closed ? "Closed" : days === null ? "No deadline" : dueIn(days)}
                    </span>
                    <span className={styles.dueDate}>
                        {call.deadline ? shortDate(call.deadline, !closed) : ""}
                        {closed && call.was ? ` · was ${WAS[call.was]}` : ""}
                        {closed && !call.listed ? " · no longer listed" : ""}
                    </span>
                </dd>
                <dt className={styles.factLabel}>Fit</dt>
                <dd className={styles.fit}>
                    {fit ? (
                        <span className={styles.fitLabel}>
                            <span aria-hidden="true" className={`${styles.marker} ${fit.marker}`} />
                            {fit.label}
                        </span>
                    ) : (
                        <span className={styles.fitLabel}>Not checked</span>
                    )}
                    {call.match !== null && call.match !== undefined && <span className={styles.match}>{call.match}% match</span>}
                </dd>
            </dl>
            <div className={styles.actions}>
                {call.stage === "saved" && (
                    <>
                        <Link href={apply} className={`${buttons.dark} ${buttons.small}`}>Open application →</Link>
                        <button type="button" className={buttons.link} onClick={() => onRemove(call)}>Remove from saved</button>
                    </>
                )}
                {call.stage === "draft" && (
                    <>
                        <Link href={apply} className={`${buttons.dark} ${buttons.small}`}>Continue →</Link>
                        <button type="button" className={buttons.link} onClick={() => onRemove(call)}>Remove</button>
                    </>
                )}
                {call.stage === "completed" && (
                    <>
                        <a href={`/api/applications/${encodeURIComponent(call.id)}/download`} download
                           className={`${buttons.dark} ${buttons.small}`}>
                            Download package →
                        </a>
                        <Link href={apply} className={`${buttons.secondary} ${buttons.small}`}>Open application →</Link>
                    </>
                )}
                {closed && <button type="button" className={buttons.link} onClick={() => onRemove(call)}>Remove</button>}
            </div>
        </li>
    );
};

export default CallRow;
