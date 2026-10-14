"use client";

import Link from "next/link";
import { useState } from "react";
import VerdictBadge from "@/components/VerdictBadge/VerdictBadge";
import { requestJson } from "@/lib/api";
import { deadlineFact } from "@/lib/discover";
import type { ApplicationData } from "@/lib/types";
import ChatPanel from "./ChatPanel";
import Checklist from "./Checklist";
import DraftPanel from "./DraftPanel";
import styles from "./Apply.module.css";

// What a narrow screen shows: one column at a time, chosen with the switch on top
type View = "checklist" | "chat" | "draft";
const VIEWS: { view: View; label: string }[] = [
    { view: "checklist", label: "Checklist" },
    { view: "chat", label: "Assistant" },
    { view: "draft", label: "Draft" },
];

// The application page (workflow.MD, "Step 6"): the checklist on the left, the chat about the
// selected item in the centre, its draft on the right. Every save answers with the whole
// application, so the checklist's states always match the server.
const ApplyWorkspace = ({ initial }: { initial: ApplicationData }) => {
    const [data, setData] = useState(initial);
    const [selected, setSelected] = useState<string | null>(initial.to_draft[0]?.key ?? null);
    const [view, setView] = useState<View>("checklist");
    const [error, setError] = useState("");
    // the artist's unsaved edits in the draft box, by item: kept when switching items, sent to the agent
    const [edits, setEdits] = useState<Record<string, string>>({});
    const item = data.to_draft.find((i) => i.key === selected) ?? null;
    const draftText = item ? (edits[item.key] ?? item.draft ?? "") : "";
    const base = `/api/applications/${encodeURIComponent(data.opportunity_id)}/items`;

    // the saved text (the artist's or the agent's) replaces the edit
    const dropEdit = (key: string) =>
        setEdits((all) => {
            const rest = { ...all };
            delete rest[key];
            return rest;
        });

    const saveItem = async (key: string, body: { draft?: string; ticked?: boolean }): Promise<string | null> => {
        const result = await requestJson<ApplicationData>("PUT", `${base}/${encodeURIComponent(key)}`, body);
        if (!result.ok) return result.error;
        setData(result.data);
        if (body.draft !== undefined) dropEdit(key);
        return null;
    };

    const confirmItem = async (key: string): Promise<string | null> => {
        const result = await requestJson<ApplicationData>("POST", `${base}/${encodeURIComponent(key)}/confirm`);
        if (!result.ok) return result.error;
        setData(result.data);
        return null;
    };

    const reviewed = data.to_draft.filter((i) => i.state === "confirmed").length;
    const gathered = data.to_gather.filter((i) => i.state === "uploaded" || i.state === "ticked").length;

    const tick = async (key: string, ticked: boolean) => setError((await saveItem(key, { ticked })) ?? "");

    const select = (key: string) => {
        setSelected(key);
        setView("chat"); // on a narrow screen, picking an item opens its conversation
    };

    return (
        <main id="main" className={styles.main}>
            <Link href={`/opportunities/${encodeURIComponent(data.opportunity_id)}`} className={styles.back}>
                ← Back to the call
            </Link>
            <header className={styles.header}>
                <p className={styles.kicker}>Draft an application</p>
                <h1 className={styles.title}>{data.title}</h1>
                <p className={styles.facts}>
                    <span>Deadline: {deadlineFact(data.deadline)}</span>
                    {data.application_language && <span>Language: {data.application_language}</span>}
                    {data.submission_method && <span>Submit by: {data.submission_method}</span>}
                </p>
                {data.verdict_status === "LIKELY_NOT_ELIGIBLE" && (
                    <p className={styles.warning}>
                        <VerdictBadge status={data.verdict_status} /> Check the call&apos;s conditions before spending
                        time on this application.
                    </p>
                )}
                <div className={styles.exportRow}>
                    <p className={styles.reviewed}>
                        Texts reviewed: {reviewed} of {data.to_draft.length} · Items gathered: {gathered} of{" "}
                        {data.to_gather.length}
                    </p>
                    {/* complete = every text reviewed, every item uploaded or ticked: the server applies the
                        same rule (api/applications.py missing) and refuses the download before that */}
                    {data.missing.length === 0 ? (
                        <a href={`/api/applications/${encodeURIComponent(data.opportunity_id)}/download`} download
                           className={styles.secondary}>
                            Download application
                        </a>
                    ) : (
                        <>
                            <button type="button" className={styles.secondary} disabled aria-describedby="download-missing">
                                Download application
                            </button>
                            <span id="download-missing" className={styles.exportHint}>
                                Still to do: {data.missing.join(" · ")}
                            </span>
                        </>
                    )}
                </div>
                <p className={styles.privacy}>
                    To draft, the assistant sends your documents&apos; relevant passages, your profile and your projects to
                    OpenAI. Nothing is sent to the call: you submit the application yourself.
                </p>
            </header>
            <p role="alert" className={styles.error}>
                {error}
            </p>

            <div className={styles.switch} role="group" aria-label="Show">
                {VIEWS.map((v) => (
                    <button key={v.view} type="button" aria-pressed={view === v.view} onClick={() => setView(v.view)}>
                        {v.label}
                    </button>
                ))}
            </div>

            <div className={styles.workspace} data-view={view}>
                <div className={styles.columnChecklist}>
                    <Checklist data={data} selected={selected} onSelect={select} onTick={tick} />
                </div>
                <div className={styles.columnChat}>
                    <ChatPanel
                        key={item?.key ?? "none"}
                        item={item}
                        itemsPath={base}
                        draft={draftText}
                        adaptStatement={item?.document === "statement" && data.documents.some((d) => d.kind === "statement")}
                        onTurn={(application) => {
                            setData(application);
                            if (item) dropEdit(item.key);
                        }}
                    />
                </div>
                <div className={styles.columnDraft}>
                    {item ? (
                        <DraftPanel
                            key={item.key}
                            item={item}
                            text={draftText}
                            onChange={(text) => setEdits((all) => ({ ...all, [item.key]: text }))}
                            onSave={(text) => saveItem(item.key, { draft: text })}
                            onConfirm={() => confirmItem(item.key)}
                        />
                    ) : (
                        <p className={styles.hint}>Nothing to draft for this call.</p>
                    )}
                </div>
            </div>
        </main>
    );
};

export default ApplyWorkspace;
