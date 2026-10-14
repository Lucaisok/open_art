"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { requestJson } from "@/lib/api";
import { thumbUrl } from "@/lib/images";
import type { AgentMessage, AgentTurn, ApplicationData, ApplicationItem, ProjectChoice, ProjectSelection } from "@/lib/types";
import { categoryLabel } from "@/components/Projects/categories";
import styles from "./Apply.module.css";

type AssistantPanelProps = {
    data: ApplicationData;
    item: ApplicationItem | null;      // the selected item to write; null for an item to gather
    itemsPath: string;                 // /api/applications/{id}/items
    draft: string;                     // the text in the draft box now, saved or not
    readOnly: boolean;
    onTurn: (application: ApplicationData) => void;
    onProjects: (selection: ProjectSelection | "suggested") => Promise<string | null>;
    onItemProjects: (selection: ProjectSelection | null) => Promise<string | null>;
};

const STATUS: Record<string, string> = { current: "Current", planned: "Planned", past: "Past" };
const statusTag = (p: ProjectChoice) =>
    p.category && p.category !== "work" ? categoryLabel(p.category) ?? "Project" : STATUS[p.status ?? ""] ?? "Project";

const listNames = (names: string[]) =>
    names.length <= 1 ? names[0] ?? "" : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;

// The right column (design: APPLICATION.md → Assistant). On top, what the assistant writes about: the
// projects this text proposes and mentions, changed in place ("Change projects"). Then the conversation
// about the selected text (one chat per text): each message is one model call on the server
// (src/agent/drafting.py), which answers here and writes a new version into the draft, to review.
// Rendered with key={item.key}: a new text, a new chat.
const AssistantPanel = ({ data, item, itemsPath, draft, readOnly, onTurn, onProjects, onItemProjects }: AssistantPanelProps) => {
    const [messages, setMessages] = useState<AgentMessage[] | null>(null);   // null = loading
    const [text, setText] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(false);
    const [lastMessage, setLastMessage] = useState("");
    const [editing, setEditing] = useState(false);
    const end = useRef<HTMLDivElement>(null);
    const path = item ? `${itemsPath}/${encodeURIComponent(item.key)}/messages` : null;

    useEffect(() => {
        if (!path) return;
        const controller = new AbortController();
        requestJson<AgentMessage[]>("GET", path, undefined, { signal: controller.signal }).then((result) => {
            if (result.ok) setMessages(result.data);
        });
        return () => controller.abort();
    }, [path]);

    useEffect(() => {
        end.current?.scrollIntoView({ block: "nearest" });
    }, [messages, busy]);

    const send = async (message: string) => {
        if (!message.trim() || busy || !path) return;
        setBusy(true);
        setError(false);
        setLastMessage(message.trim());
        const result = await requestJson<AgentTurn>("POST", path, { message: message.trim(), draft });
        setBusy(false);
        if (!result.ok) {
            setError(true);
            return;
        }
        setText("");
        setMessages(result.data.messages);
        onTurn(result.data.application);
    };

    // -- the projects this text is about ---------------------------------------------------------------
    const byId = new Map(data.projects.map((p) => [p.id, p]));
    const own = item?.projects ?? null;                       // this text's own choice, if any
    const selection = own ?? data.selection;
    const proposed = selection.proposing ? byId.get(selection.proposing) : undefined;
    const mentioned = (selection.mention ?? []).map((id) => byId.get(id)).filter(Boolean) as ProjectChoice[];
    const bandText = proposed
        ? `${proposed.title} is the project you propose${mentioned.length ? `; ${listNames(mentioned.map((p) => p.title))} ${mentioned.length === 1 ? "gets" : "get"} a short mention.` : "."}`
        : mentioned.length
          ? `No project is proposed; ${listNames(mentioned.map((p) => p.title))} ${mentioned.length === 1 ? "gets" : "get"} a short mention.`
          : "Your practice in general: no project is named.";
    const bandCards = [...(proposed ? [{ p: proposed, role: "Proposed" }] : []), ...mentioned.map((p) => ({ p, role: "Mentioned" }))];

    // the list below edits this text's own choice, or the application's ("Your choice")
    const editingOwn = own !== null;
    const editable = editingOwn || data.selection_chosen;
    const change = (next: ProjectSelection) => (editingOwn ? onItemProjects(next) : onProjects(next));
    const include = (p: ProjectChoice, on: boolean) => {
        const mention = (selection.mention ?? []).filter((id) => id !== p.id);
        change({
            proposing: on ? selection.proposing : selection.proposing === p.id ? null : selection.proposing,
            mention: on && selection.proposing !== p.id ? [...mention, p.id] : mention,
        });
    };
    const propose = (p: ProjectChoice | null) =>
        change({ proposing: p?.id ?? null, mention: (selection.mention ?? []).filter((id) => id !== p?.id) });

    if (!item) {
        return (
            <section aria-label="Assistant" className={styles.assistant}>
                <div className={styles.assistantHead}>
                    <h2 className={styles.columnHeadPlain}>Assistant</h2>
                </div>
                <div className={styles.thread}>
                    <div className={styles.agentBlock}>
                        <span className={styles.who}>Assistant</span>
                        <p>{data.to_draft.length
                            ? "Pick a text in the checklist and I'll help you draft it."
                            : "This call asks for nothing written: gather the items in the checklist, then download the package."}</p>
                    </div>
                </div>
            </section>
        );
    }

    const starter = item.document === "statement" && data.documents.some((d) => d.kind === "statement")
        ? "Adapt my statement" : "Write a first draft";
    return (
        <section aria-label="Assistant" className={styles.assistant}>
            <div className={styles.assistantHead}>
                <h2 className={styles.columnHeadPlain}>Assistant</h2>
                <span className={styles.workingOn}>Working on: {item.title}{item.limit ? ` · ${item.limit}` : ""}</span>
            </div>

            <div className={styles.band}>
                <div className={styles.bandHead}>
                    <span className={styles.eyebrowMuted}>What the assistant writes about</span>
                    {!readOnly && (
                        <button type="button" className={styles.bandToggle} aria-expanded={editing} onClick={() => setEditing(!editing)}>
                            {editing ? "Done" : "Change projects"}
                        </button>
                    )}
                </div>
                <p className={styles.bandText}>{bandText}</p>
                {bandCards.length > 0 && (
                    <div className={styles.bandCards}>
                        {bandCards.map(({ p, role }) => (
                            <button key={p.id} type="button" className={`${styles.bandCard} ${role === "Proposed" ? styles.bandCardLead : ""}`}
                                    onClick={() => !readOnly && setEditing(true)}>
                                {p.images[0] ? (
                                    // eslint-disable-next-line @next/next/no-img-element
                                    <img src={thumbUrl(p.images[0].id)} alt="" className={styles.bandThumb} />
                                ) : (
                                    <span className={styles.bandThumb} aria-hidden="true" />
                                )}
                                <span className={styles.bandCardText}>
                                    <span className={styles.bandCardTitle}>{p.title}</span>
                                    <span className={role === "Proposed" ? styles.roleLead : styles.role}>{role}</span>
                                </span>
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {editing ? (
                <div className={styles.projectEditor}>
                    <div role="radiogroup" aria-label="Projects for this text" className={styles.forText}>
                        <span className={styles.eyebrowMuted}>For {item.title}</span>
                        <label className={styles.radioLine}>
                            <input type="radio" name="text-projects" checked={!editingOwn} onChange={() => onItemProjects(null)} />
                            <span>Same as the application</span>
                        </label>
                        <label className={styles.radioLine}>
                            <input type="radio" name="text-projects" checked={editingOwn} onChange={() => onItemProjects(data.selection)} />
                            <span>Choose for this text</span>
                        </label>
                    </div>
                    {!editingOwn && (
                        <div role="radiogroup" aria-label="Project choice" className={styles.modeTabs}>
                            <button type="button" role="radio" aria-checked={!data.selection_chosen} className={styles.modeTab}
                                    onClick={() => data.selection_chosen && onProjects("suggested")}>Suggested</button>
                            <button type="button" role="radio" aria-checked={data.selection_chosen} className={styles.modeTab}
                                    onClick={() => !data.selection_chosen && onProjects(data.selection)}>Your choice</button>
                        </div>
                    )}
                    {!editable && <p className={styles.modeNote}>The projects closest to this call. Switch to Your choice to change them.</p>}
                    {editable && (
                        <label className={`${styles.radioLine} ${styles.proposeNone}`}>
                            <input type="radio" name="propose" checked={!selection.proposing} onChange={() => propose(null)} />
                            <span>Propose none: the call is about my practice</span>
                        </label>
                    )}
                    {data.projects.length === 0 && (
                        <p className={styles.modeNote}>No saved projects yet: the assistant writes about your practice.</p>
                    )}
                    {data.projects.map((p) => {
                        const isProposed = selection.proposing === p.id;
                        const isMentioned = (selection.mention ?? []).includes(p.id);
                        const included = isProposed || isMentioned;
                        return (
                            <div key={p.id} className={`${styles.choice} ${isProposed ? styles.choiceLead : included ? styles.choiceOn : styles.choiceOff}`}>
                                {p.images[0] ? (
                                    // eslint-disable-next-line @next/next/no-img-element
                                    <img src={thumbUrl(p.images[0].id)} alt="" className={styles.choiceThumb} />
                                ) : (
                                    <span className={styles.choiceThumb} aria-hidden="true" />
                                )}
                                <span className={styles.choiceText}>
                                    <span className={styles.choiceTitle}>{p.title}</span>
                                    <span className={styles.muted}>{[p.years, p.medium].filter(Boolean).join(" · ")}</span>
                                    <span className={styles.choiceTags}>
                                        <span className={styles.tag}>{statusTag(p)}</span>
                                        <span className={included ? styles.roleOn : styles.roleOff}>
                                            {isProposed ? "Proposing" : isMentioned ? "Also mention" : "Not included"}
                                        </span>
                                    </span>
                                </span>
                                {editable && (
                                    <span className={styles.choiceControls}>
                                        <label className={styles.radioLine}>
                                            <input type="checkbox" checked={included} onChange={(e) => include(p, e.target.checked)} />
                                            <span>Include</span>
                                        </label>
                                        {p.can_propose && (
                                            <label className={styles.radioLine}>
                                                <input type="radio" name="propose" checked={isProposed} onChange={() => propose(p)} />
                                                <span>Propose</span>
                                            </label>
                                        )}
                                    </span>
                                )}
                            </div>
                        );
                    })}
                    <Link href="/studio" className={styles.smallLink}>Add or edit projects</Link>
                    <button type="button" className={styles.darkButton} onClick={() => setEditing(false)}>Done</button>
                </div>
            ) : (
                <div className={styles.thread} aria-live="polite">
                    {messages === null && <p className={styles.muted}>Loading the conversation…</p>}
                    {messages !== null && messages.length === 0 && !busy && (
                        <div className={styles.agentBlock}>
                            <span className={styles.who}>Assistant</span>
                            <p>I draft from your documents, profile, projects and the other texts of this application. You edit and review every word.</p>
                            {!readOnly && (
                                <button type="button" className={styles.darkButton} onClick={() => send(`${starter}.`)}>{starter} →</button>
                            )}
                        </div>
                    )}
                    {messages?.map((m, i) =>
                        m.role === "artist" ? (
                            <div key={i} className={styles.youBlock}>
                                <span className={styles.who}>You</span>
                                <p>{m.content}</p>
                            </div>
                        ) : (
                            <div key={i} className={styles.agentBlock}>
                                <span className={styles.who}>Assistant</span>
                                <p>{m.content}</p>
                                {m.wrote_words !== null && m.wrote_words !== undefined && (
                                    <span className={styles.wrote}>
                                        <span aria-hidden="true" className={styles.limeMarker} />Wrote a new version · {m.wrote_words} words
                                    </span>
                                )}
                                {m.sources.length > 0 && <span className={styles.sources}>Based on: {m.sources.join(" · ")}</span>}
                            </div>
                        ),
                    )}
                    {busy && (
                        <div role="status" className={styles.typing}>
                            <span aria-hidden="true" className={styles.dots}><span /><span /><span /></span>
                            <span>The assistant is writing…</span>
                        </div>
                    )}
                    {error && (
                        <p role="alert" className={styles.assistantError}>
                            The assistant isn&apos;t available right now, try again.{" "}
                            <button type="button" onClick={() => send(lastMessage)}>Try again</button>
                        </p>
                    )}
                    <div ref={end} />
                </div>
            )}

            {!readOnly && !editing && (
                <>
                    <form className={styles.composer} onSubmit={(event) => {
                        event.preventDefault();
                        send(text);
                    }}>
                        <label htmlFor="composer" className={styles.visuallyHidden}>Message the assistant</label>
                        <textarea id="composer" rows={2} value={text} maxLength={4000}
                                  placeholder="Ask for changes: shorter, more about the project, mention…"
                                  onChange={(event) => setText(event.target.value)}
                                  onKeyDown={(event) => {
                                      if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                                          event.preventDefault();
                                          send(text);
                                      }
                                  }} />
                        <button type="submit" disabled={busy || !text.trim()}>Send</button>
                    </form>
                    <span className={styles.composerNote}>
                        Enter to send · Shift+Enter for a new line. To draft, the assistant sends your documents&apos; relevant
                        passages, your profile and your projects to OpenAI. Nothing is sent to the call.
                    </span>
                </>
            )}
        </section>
    );
};

export default AssistantPanel;
