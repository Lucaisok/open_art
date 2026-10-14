"use client";

import { useEffect, useRef, useState } from "react";
import { requestJson } from "@/lib/api";
import type { AgentMessage, AgentTurn, ApplicationData, ApplicationItem } from "@/lib/types";
import styles from "./Apply.module.css";

type ChatPanelProps = {
    item: ApplicationItem | null;
    itemsPath: string;               // /api/applications/{id}/items
    draft: string;                   // the text in the draft box now, saved or not
    adaptStatement: boolean;         // the item is a statement and one is uploaded
    onTurn: (application: ApplicationData) => void;
};

// The centre column: the conversation with the agent about the selected item (one chat per item).
// Each message is one model call on the server (src/agent/drafting.py), which answers here and
// writes a new draft on the right, to review. Rendered with key={item.key}: a new item, a new chat.
const ChatPanel = ({ item, itemsPath, draft, adaptStatement, onTurn }: ChatPanelProps) => {
    const [messages, setMessages] = useState<AgentMessage[] | null>(null);   // null = loading
    const [text, setText] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const end = useRef<HTMLDivElement>(null);
    const path = item ? `${itemsPath}/${encodeURIComponent(item.key)}/messages` : null;

    // this item's earlier messages
    useEffect(() => {
        if (!path) return;
        const controller = new AbortController();
        requestJson<AgentMessage[]>("GET", path, undefined, { signal: controller.signal }).then((result) => {
            if (result.ok) setMessages(result.data);
            else if (result.status !== 0) setError(result.error);
        });
        return () => controller.abort();
    }, [path]);

    // keep the newest message in view
    useEffect(() => {
        end.current?.scrollIntoView({ block: "nearest" });
    }, [messages, busy]);

    if (!item || !path) {
        return (
            <section aria-labelledby="chat-heading" className={styles.chat}>
                <h2 id="chat-heading" className={styles.columnTitle}>
                    Assistant
                </h2>
                <p className={styles.hint}>
                    This call asks for nothing written: gather the items on the checklist and apply on the call&apos;s
                    own site.
                </p>
            </section>
        );
    }

    const send = async (message: string) => {
        if (!message.trim() || busy) return;
        setBusy(true);
        setError("");
        const result = await requestJson<AgentTurn>("POST", path, { message: message.trim(), draft });
        setBusy(false);
        if (!result.ok) {
            setError(result.error);
            return;
        }
        setText("");
        setMessages(result.data.messages);
        onTurn(result.data.application);
    };

    const starter = adaptStatement ? "Adapt my statement for this call." : "Write a first draft.";

    return (
        <section aria-labelledby="chat-heading" className={styles.chat}>
            <h2 id="chat-heading" className={styles.columnTitle}>
                Assistant
            </h2>
            <p className={styles.chatAbout}>
                Working on: <strong>{item.title}</strong>
                {item.limit && <span className={styles.itemLimit}> · {item.limit}</span>}
            </p>

            <div className={styles.messages}>
                {messages === null ? (
                    <p className={styles.hint}>Loading the conversation…</p>
                ) : messages.length === 0 ? (
                    <div className={styles.start}>
                        <p className={styles.hint}>
                            The assistant drafts from your documents, profile and projects, and from the other
                            texts of this application. Ask it for a first version, then tell it what to change.
                        </p>
                        <button type="button" className={styles.primary} onClick={() => send(starter)} disabled={busy}>
                            {adaptStatement ? "Adapt my statement" : "Write a first draft"}
                        </button>
                    </div>
                ) : (
                    <ol className={styles.messageList} aria-label="Conversation">
                        {messages.map((m, i) => (
                            <li key={i} className={m.role === "artist" ? styles.fromArtist : styles.fromAgent}>
                                <span className={styles.visuallyHidden}>{m.role === "artist" ? "You:" : "Assistant:"}</span>
                                <p className={styles.messageText}>{m.content}</p>
                                {m.sources.length > 0 && (
                                    <p className={styles.sources}>Based on: {m.sources.join("; ")}</p>
                                )}
                            </li>
                        ))}
                    </ol>
                )}
                <p aria-live="polite" className={styles.hint}>
                    {busy ? "The assistant is writing…" : ""}
                </p>
                <div ref={end} />
            </div>

            <p role="alert" className={styles.error}>
                {error}
            </p>
            <form
                className={styles.composer}
                onSubmit={(event) => {
                    event.preventDefault();
                    send(text);
                }}
            >
                <label htmlFor="chat-message" className={styles.visuallyHidden}>
                    Message to the assistant
                </label>
                <textarea
                    id="chat-message"
                    className={styles.composerInput}
                    rows={3}
                    value={text}
                    maxLength={4000}
                    placeholder="Ask for changes: shorter, more about the project, mention…"
                    onChange={(event) => setText(event.target.value)}
                    onKeyDown={(event) => {
                        // Enter sends, Shift+Enter is a new line
                        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                            event.preventDefault();
                            send(text);
                        }
                    }}
                />
                <button type="submit" className={styles.primary} disabled={busy || !text.trim()}>
                    Send
                </button>
            </form>
        </section>
    );
};

export default ChatPanel;
