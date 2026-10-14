"use client";

import Link from "next/link";
import { useState } from "react";
import { requestJson } from "@/lib/api";
import { DOCUMENT_NAMES } from "@/lib/apply";
import { daysUntil, deadlineFact, placeLabel } from "@/lib/discover";
import type { ApplicationData, ProjectSelection } from "@/lib/types";
import SaveCall from "@/components/SaveCall/SaveCall";
import { useToast } from "@/components/ui/Toast";
import AssistantPanel from "./AssistantPanel";
import Checklist from "./Checklist";
import DraftColumn from "./DraftColumn";
import ImagePicker from "./ImagePicker";
import styles from "./Apply.module.css";

// What a screen under 1100 px shows: one column at a time, chosen with the tabs on top
type View = "checklist" | "draft" | "assistant";
const VIEWS: { view: View; label: string }[] = [
    { view: "checklist", label: "Checklist" },
    { view: "draft", label: "Draft" },
    { view: "assistant", label: "Assistant" },
];

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

// What the downloaded zip holds, in words, for the header and the "Everything is ready" banner
const zipContents = (data: ApplicationData) => {
    const parts = [plural(data.to_draft.length, "text", "texts"), "application.docx", "a checklist"];
    for (const item of data.to_gather) {
        if (item.state === "uploaded" && item.document) parts.push(`your ${DOCUMENT_NAMES[item.document] ?? item.document}`);
        if (item.state === "chosen") parts.push(`${plural(item.images.length, "image", "images")} for ${item.title.toLowerCase()}`);
    }
    return parts.join(", ");
};

// The application page (design: APPLICATION.md). On top: the call, Save, Download (only once
// everything is ready), the deadline and the progress. Then three columns: the checklist; the
// selected text's draft (or the selected item to gather); the assistant. Every save answers with the
// whole application, so the checklist's states always match the server. Human in the loop: only the
// artist's "I have reviewed this" marks a text reviewed, and nothing is ever sent to the call.
const ApplyWorkspace = ({ initial }: { initial: ApplicationData }) => {
    const toast = useToast();
    const [data, setData] = useState(initial);
    const [selected, setSelected] = useState<string | null>(initial.to_draft[0]?.key ?? initial.to_gather[0]?.key ?? null);
    const [view, setView] = useState<View>("draft");
    const [error, setError] = useState("");
    // the artist's unsaved edits in the draft box, by item: kept when switching items, sent to the agent
    const [edits, setEdits] = useState<Record<string, string>>({});
    // "New version from the assistant": shown on an item after a turn rewrote its draft
    const [cues, setCues] = useState<Record<string, boolean>>({});
    const [picking, setPicking] = useState<string | null>(null);   // the item whose images are being chosen

    const text = data.to_draft.find((i) => i.key === selected) ?? null;
    const gather = data.to_gather.find((i) => i.key === selected) ?? null;
    const draftText = text ? (edits[text.key] ?? text.draft ?? "") : "";
    const base = `/api/applications/${encodeURIComponent(data.opportunity_id)}`;
    const closed = data.deadline !== null && daysUntil(data.deadline) < 0;
    const complete = data.missing.length === 0 && !closed;

    const dropEdit = (key: string) =>
        setEdits((all) => {
            const rest = { ...all };
            delete rest[key];
            return rest;
        });

    const call = async (method: "PUT" | "POST" | "DELETE", path: string, body?: unknown): Promise<string | null> => {
        const result = await requestJson<ApplicationData>(method, path, body);
        if (!result.ok) {
            setError(result.error);
            return result.error;
        }
        setError("");
        setData(result.data);
        return null;
    };
    const saveDraft = async (key: string, draft: string) => {
        const problem = await call("PUT", `${base}/items/${encodeURIComponent(key)}`, { draft });
        if (!problem) dropEdit(key);
        return problem;
    };
    const review = async (key: string) => {
        // the text the artist sees is the one reviewed: an unsaved edit is saved first
        if (edits[key] !== undefined && (await saveDraft(key, edits[key]))) return;
        if (!(await call("POST", `${base}/items/${encodeURIComponent(key)}/confirm`))) toast("Reviewed by you");
    };
    const tick = (key: string, ticked: boolean) => call("PUT", `${base}/items/${encodeURIComponent(key)}`, { ticked });
    const chooseImages = async (key: string, ids: string[]) => {
        if (!(await call("PUT", `${base}/items/${encodeURIComponent(key)}/images`, { ids }))) {
            setPicking(null);
            toast(ids.length ? "Images chosen" : "Images removed");
        }
    };
    const chooseProjects = (selection: ProjectSelection | "suggested") =>
        selection === "suggested" ? call("DELETE", `${base}/projects`) : call("PUT", `${base}/projects`, selection);
    const chooseItemProjects = (key: string, selection: ProjectSelection | null) =>
        call("PUT", `${base}/items/${encodeURIComponent(key)}/projects`, { selection });

    const select = (key: string) => {
        setSelected(key);
        setView("draft"); // under 1100 px, picking an item opens its draft
    };

    const reviewed = data.to_draft.filter((i) => i.state === "confirmed").length;
    const gathered = data.to_gather.filter((i) => ["uploaded", "chosen", "ticked"].includes(i.state)).length;
    const days = data.deadline ? daysUntil(data.deadline) : null;
    const urgent = !closed && days !== null && days < 7;
    const download = `${base}/download`;
    const pickerItem = data.to_gather.find((i) => i.key === picking) ?? null;
    const progress: [string, number, number][] = [
        ["Texts reviewed", reviewed, data.to_draft.length],
        ["Items gathered", gathered, data.to_gather.length],
    ];

    return (
        <main id="main" className={styles.main}>
            <section aria-labelledby="h-app" className={styles.header}>
                <Link href={`/opportunities/${encodeURIComponent(data.opportunity_id)}`} className={styles.back}>
                    ← Back to the call
                </Link>
                <div className={styles.titleRow}>
                    <div className={styles.titleText}>
                        <span className={styles.eyebrow}>Draft an application</span>
                        <h1 id="h-app" className={styles.title}>{data.title}</h1>
                        <span className={styles.byline}>
                            {[data.organisation, placeLabel(data.city, data.countries)].filter(Boolean).join(" · ")}
                        </span>
                    </div>
                    <div className={styles.headerActions}>
                        <div className={styles.headerButtons}>
                            <SaveCall id={data.opportunity_id} title={data.title} initial={data.saved} look="application" />
                            {complete ? (
                                <a href={download} download className={styles.downloadReady}
                                   onClick={() => toast("Application downloaded")}>
                                    Download application →
                                </a>
                            ) : (
                                <button type="button" className={styles.downloadOff} disabled aria-describedby="todo-line">
                                    Download application
                                </button>
                            )}
                        </div>
                        <span id="todo-line" className={styles.todo}>
                            {closed ? "This call is closed." : complete ? `Contains: ${zipContents(data)}.` : `Still to do: ${data.missing.join(" · ")}`}
                        </span>
                    </div>
                </div>

                <dl className={styles.factStrip}>
                    <div className={styles.fact}>
                        <dt className={styles.factLabel}>Deadline</dt>
                        <dd className={`${styles.factValue} ${urgent ? styles.urgent : ""} ${closed ? styles.closedText : ""}`}>
                            {closed ? `${deadlineFact(data.deadline).split(" · ")[0]} · closed` : deadlineFact(data.deadline)}
                        </dd>
                    </div>
                    <div className={styles.fact}>
                        <dt className={styles.factLabel}>Submit by</dt>
                        <dd className={styles.factValue}>
                            {data.submission_method
                                ? data.submission_method.charAt(0).toUpperCase() + data.submission_method.slice(1)
                                : "On the call's own site"}
                        </dd>
                    </div>
                    {progress.map(([label, done, total]) => (
                        <div key={label} className={styles.fact}>
                            <dt className={`${styles.factLabel} ${styles.progressLabel}`}>
                                <span>{label}</span>
                                <span className={styles.progressCount}>{done} of {total}</span>
                            </dt>
                            <dd className={styles.progressTrack}>
                                <span className={`${styles.progressBar} ${done === total ? styles.progressFull : ""}`}
                                      style={{ width: `${total ? Math.round((done / total) * 100) : 100}%` }} />
                            </dd>
                        </div>
                    ))}
                </dl>

                {data.verdict_status === "LIKELY_NOT_ELIGIBLE" && !closed && (
                    <div role="note" className={styles.bannerWarn}>
                        <span className={styles.bannerStrong}>
                            <span aria-hidden="true" className={styles.inkMarker} />Likely not eligible
                        </span>
                        <span>Check the call&apos;s conditions before spending time on this application.</span>
                    </div>
                )}
                {closed && (
                    <div role="note" className={styles.bannerClosed}>
                        <span className={styles.bannerStrong}>This call is closed</span>
                        <span>The deadline was {deadlineFact(data.deadline).split(" · ")[0]}. Your drafts are kept, read-only.</span>
                    </div>
                )}
                {complete && (
                    <div role="status" className={styles.bannerReady}>
                        <span className={styles.readyText}>
                            <span className={styles.readyTitle}>Everything is ready</span>
                            <span>The zip holds {zipContents(data)}. Submit it on the call&apos;s own site: OpenArt never sends it for you.</span>
                        </span>
                        <a href={download} download className={styles.darkButton} onClick={() => toast("Application downloaded")}>
                            Download application →
                        </a>
                    </div>
                )}
                {data.documents.length === 0 && (
                    <Link href="/studio" className={styles.docsHint}>
                        You have no documents yet. Add your documents for better drafts →
                    </Link>
                )}
                {error && <p role="alert" className={styles.error}>{error}</p>}
            </section>

            <div role="tablist" aria-label="Application sections" className={styles.switch}>
                {VIEWS.map((v) => (
                    <button key={v.view} type="button" role="tab" aria-selected={view === v.view} onClick={() => setView(v.view)}>
                        {v.label}
                    </button>
                ))}
            </div>

            <div className={styles.workspace} data-view={view}>
                <div className={styles.columnChecklist}>
                    <Checklist data={data} selected={selected} readOnly={closed} onSelect={select} onTick={tick}
                               onChooseImages={(key) => setPicking(key)} />
                </div>
                <div className={styles.columnDraft}>
                    <DraftColumn
                        key={selected ?? "none"}
                        data={data}
                        text={text}
                        gather={gather}
                        draft={draftText}
                        readOnly={closed}
                        cue={text ? Boolean(cues[text.key]) : false}
                        onDismissCue={() => text && setCues((c) => ({ ...c, [text.key]: false }))}
                        onChange={(value) => {
                            if (!text) return;
                            setEdits((all) => ({ ...all, [text.key]: value }));
                            setCues((c) => ({ ...c, [text.key]: false }));
                        }}
                        onSave={(value) => (text ? saveDraft(text.key, value) : Promise.resolve(null))}
                        onReview={() => (text ? review(text.key) : Promise.resolve())}
                        onTick={(ticked) => {
                            if (gather) tick(gather.key, ticked);
                        }}
                        onChooseImages={() => gather && setPicking(gather.key)}
                    />
                </div>
                <div className={styles.columnAssistant}>
                    <AssistantPanel
                        key={text?.key ?? "none"}
                        data={data}
                        item={text}
                        itemsPath={`${base}/items`}
                        draft={draftText}
                        readOnly={closed}
                        onTurn={(application) => {
                            if (!text) return;
                            const before = text.draft ?? "";
                            const after = application.to_draft.find((i) => i.key === text.key)?.draft ?? "";
                            setData(application);
                            dropEdit(text.key);
                            if (after !== before) setCues((c) => ({ ...c, [text.key]: true }));
                        }}
                        onProjects={chooseProjects}
                        onItemProjects={(selection) => (text ? chooseItemProjects(text.key, selection) : Promise.resolve(null))}
                    />
                </div>
            </div>

            {pickerItem && (
                <ImagePicker item={pickerItem} choices={data.image_choices} onClose={() => setPicking(null)}
                             onUse={(ids) => chooseImages(pickerItem.key, ids)} />
            )}
        </main>
    );
};

export default ApplyWorkspace;
