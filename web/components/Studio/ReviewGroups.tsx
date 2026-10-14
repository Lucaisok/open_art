"use client";

import { useState } from "react";
import { thumbUrl } from "@/lib/images";
import type { ProjectItem } from "@/lib/types";
import buttons from "@/components/ui/buttons.module.css";
import styles from "./ReviewGroups.module.css";

// What the artist decided for one suggestion: keep it or not, and for a work whether it is current
export type Pick = { keep: boolean; current: boolean };
export type Picks = Record<string, Pick>;

// Everything kept to start with, as a value read from a document starts filled in; "current" as the
// rules read it from the years ("2024–", "2025–2026")
export const startingPicks = (suggestions: ProjectItem[]): Picks =>
    Object.fromEntries(suggestions.map((s) => [s.suggestion_key!, { keep: true, current: s.status === "current" }]));

const pickOf = (picks: Picks, s: ProjectItem): Pick =>
    picks[s.suggestion_key!] ?? { keep: true, current: s.status === "current" };

// What POST /api/projects/review takes. Only a work's status changes: an unticked "current" becomes
// past, a planned work stays planned unless ticked.
export const reviewPayload = (suggestions: ProjectItem[], picks: Picks) => {
    const accept: { key: string; status?: "past" | "current" | "planned" }[] = [];
    const dismiss: string[] = [];
    for (const s of suggestions) {
        const pick = pickOf(picks, s);
        if (!pick.keep) dismiss.push(s.suggestion_key!);
        else if (s.kind === "project" && s.category === "work")
            accept.push({ key: s.suggestion_key!, status: pick.current ? "current" : s.status === "current" ? "past" : s.status ?? "past" });
        else accept.push({ key: s.suggestion_key! });
    }
    return { accept, dismiss };
};

export const keptCount = (suggestions: ProjectItem[], picks: Picks) => suggestions.filter((s) => pickOf(picks, s).keep).length;

const GROUPS = [
    { key: "work", label: "Works", has: (s: ProjectItem) => s.kind === "project" && (s.category ?? "work") === "work" },
    { key: "exhibition", label: "Exhibitions & screenings", has: (s: ProjectItem) => s.kind === "project" && s.category === "exhibition" },
    { key: "performance", label: "Performances", has: (s: ProjectItem) => s.kind === "project" && s.category === "performance" },
    { key: "commission", label: "Commissions", has: (s: ProjectItem) => s.kind === "project" && s.category === "commission" },
    { key: "interest", label: "Interests", has: (s: ProjectItem) => s.kind === "interest", chips: true },
];

type ReviewGroupsProps = {
    suggestions: ProjectItem[];
    picks: Picks;
    onChange: (picks: Picks) => void;
};

// The projects found in the artist's documents, grouped (design: STUDIO.md → Onboarding step 3):
// each group with "n of m" and Untick all / Tick all; each item a keep tick, title, years · medium,
// two lines of description, up to 4 images, "Current project" (works) and "Show where it says so".
// Unticked items fade. Interests are toggle chips. Used by the onboarding's Projects step and by the
// Studio's "Review" modal for documents uploaded later.
const ReviewGroups = ({ suggestions, picks, onChange }: ReviewGroupsProps) => {
    const [open, setOpen] = useState<string | null>(null);   // the item whose source quote is shown
    const set = (s: ProjectItem, change: Partial<Pick>) =>
        onChange({ ...picks, [s.suggestion_key!]: { ...pickOf(picks, s), ...change } });
    const setAll = (items: ProjectItem[], keep: boolean) =>
        onChange({ ...picks, ...Object.fromEntries(items.map((s) => [s.suggestion_key!, { ...pickOf(picks, s), keep }])) });

    return (
        <div className={styles.groups}>
            {GROUPS.map((group) => {
                const items = suggestions.filter(group.has);
                if (items.length === 0) return null;
                const kept = items.filter((s) => pickOf(picks, s).keep).length;
                const allKept = kept === items.length;
                return (
                    <section key={group.key} className={styles.group} aria-labelledby={`found-${group.key}`}>
                        <div className={styles.head}>
                            <h2 id={`found-${group.key}`} className={styles.title}>
                                {group.label} <span className={styles.count}>{kept} of {items.length}</span>
                            </h2>
                            <button type="button" className={buttons.link} onClick={() => setAll(items, !allKept)}>
                                {allKept ? "Untick all" : "Tick all"}
                            </button>
                        </div>
                        {group.chips ? (
                            <div className={styles.chips}>
                                {items.map((s) => {
                                    const { keep } = pickOf(picks, s);
                                    return (
                                        <button key={s.suggestion_key} type="button" aria-pressed={keep} className={styles.chip}
                                                onClick={() => set(s, { keep: !keep })}>
                                            <span aria-hidden="true">{keep ? "✓" : "+"}</span> {s.summary}
                                        </button>
                                    );
                                })}
                            </div>
                        ) : (
                            <div className={styles.cards}>
                                {items.map((s) => {
                                    const { keep, current } = pickOf(picks, s);
                                    const meta = [s.years, s.medium].filter(Boolean).join(" · ");
                                    const source = s.sources[0];
                                    const showing = open === s.suggestion_key;
                                    return (
                                        <article key={s.suggestion_key} className={`${styles.card} ${keep ? "" : styles.off}`}>
                                            <label className={styles.keep}>
                                                <input type="checkbox" checked={keep} onChange={(e) => set(s, { keep: e.target.checked })}
                                                       aria-label={`Keep ${s.title ?? "this project"}`} />
                                                <span className={styles.keepText}>
                                                    <span className={styles.name}>{s.title ?? "Untitled project"}</span>
                                                    {meta && <span className={styles.meta}>{meta}</span>}
                                                    {s.venues.length > 0 && <span className={styles.meta}>At {s.venues.join("; ")}</span>}
                                                </span>
                                            </label>
                                            {s.summary && <p className={styles.summary}>{s.summary}</p>}
                                            {s.images.length > 0 && (
                                                <div className={styles.thumbs}>
                                                    {s.images.slice(0, 4).map((image, n) => (
                                                        // eslint-disable-next-line @next/next/no-img-element
                                                        <img key={image.id} src={thumbUrl(image.id)} loading="lazy"
                                                             alt={`${s.title ?? "Project"}, image ${n + 1} of ${s.images.length}`} />
                                                    ))}
                                                </div>
                                            )}
                                            <div className={styles.foot}>
                                                {group.key === "work" && keep && (
                                                    <label className={styles.current}>
                                                        <input type="checkbox" checked={current}
                                                               onChange={(e) => set(s, { current: e.target.checked })} />
                                                        <span>Current project</span>
                                                    </label>
                                                )}
                                                {source && (
                                                    <button type="button" className={buttons.link} aria-expanded={showing}
                                                            onClick={() => setOpen(showing ? null : s.suggestion_key!)}>
                                                        {showing ? "Hide source" : "Show where it says so"}
                                                    </button>
                                                )}
                                            </div>
                                            {showing && source && (
                                                <div className={buttons.quote}>
                                                    <span className={buttons.quoteSource}>{source.citation}</span>“{source.quote}”
                                                </div>
                                            )}
                                        </article>
                                    );
                                })}
                            </div>
                        )}
                    </section>
                );
            })}
        </div>
    );
};

export default ReviewGroups;
