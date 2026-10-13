"use client";

import { useState } from "react";
import { requestJson } from "@/lib/api";
import type { ProjectInput, ProjectItem, ProjectsData } from "@/lib/types";
import ProjectForm from "./ProjectForm";
import styles from "./Projects.module.css";

// What the form is open for: adding, editing a saved item, or accepting a suggestion with changes
type Editing =
    | { mode: "add"; start: ProjectInput }
    | { mode: "edit"; id: string; start: ProjectInput }
    | { mode: "accept"; start: ProjectInput }
    | null;

const PAST_SHOWN = 3; // the past is a timeline: the newest few, the rest behind "Show all"

const EMPTY_PROJECT: ProjectInput = { kind: "project", status: "current", venues: [] };
const EMPTY_INTEREST: ProjectInput = { kind: "interest", venues: [] };

// The fields the API takes back (a saved item or a suggestion carries more: id, sources...)
const toInput = (item: ProjectItem): ProjectInput => ({
    kind: item.kind, title: item.title, status: item.status, years: item.years, summary: item.summary,
    medium: item.medium, venues: item.venues, suggestion_key: item.suggestion_key,
});

// One project or interest: title, when, medium, the artist's words, where it was shown, and (for
// the ones read from documents) the lines it came from, behind a disclosure.
const Card = ({ item, children }: { item: ProjectItem; children: React.ReactNode }) => {
    const meta = [item.years, item.medium].filter(Boolean).join(" · ");
    return (
        <li className={`${styles.card} ${item.status === "current" ? styles.cardNow : ""}`}>
            {item.kind === "project" && <h3 className={styles.cardTitle}>{item.title ?? "Untitled project"}</h3>}
            {meta && <p className={styles.meta}>{meta}</p>}
            {item.summary && <p className={styles.summary}>{item.summary}</p>}
            {item.venues.length > 0 && <p className={styles.meta}>Shown at {item.venues.join("; ")}</p>}
            {item.sources.length > 0 && (
                <details className={styles.sources}>
                    <summary>From your documents</summary>
                    <ul>
                        {item.sources.map((source, i) => (
                            <li key={i}>
                                “{source.quote}” <span className={styles.citation}>{source.citation}</span>
                            </li>
                        ))}
                    </ul>
                </details>
            )}
            <div className={styles.cardActions}>{children}</div>
        </li>
    );
};

const ProjectsBoard = ({ initial }: { initial: ProjectsData }) => {
    const [data, setData] = useState(initial);
    const [editing, setEditing] = useState<Editing>(null);
    const [error, setError] = useState<string | null>(null);
    const [showAllPast, setShowAllPast] = useState(false);

    // every change is followed by a fresh read, so the lists and suggestions always match the server
    const reload = async () => {
        const fresh = await requestJson<ProjectsData>("GET", "/api/projects");
        if (fresh.ok) {
            setData(fresh.data);
        }
    };

    const save = async (values: ProjectInput): Promise<string | null> => {
        const result = editing?.mode === "edit"
            ? await requestJson("PUT", `/api/projects/${editing.id}`, values)
            : await requestJson("POST", "/api/projects", values);
        if (!result.ok) {
            return result.error;
        }
        setEditing(null);
        await reload();
        return null;
    };

    const act = async (method: "POST" | "DELETE", path: string, body?: unknown) => {
        const result = await requestJson(method, path, body);
        setError(result.ok ? null : result.error);
        await reload();
    };

    const now = data.projects.filter((p) => p.status === "current");
    const next = data.projects.filter((p) => p.status === "planned");
    const past = data.projects.filter((p) => p.status === "past");
    const pastShown = showAllPast ? past : past.slice(0, PAST_SHOWN);

    const savedActions = (item: ProjectItem) => (
        <>
            <button type="button" className={styles.secondary}
                    onClick={() => setEditing({ mode: "edit", id: item.id!, start: toInput(item) })}>
                Edit
            </button>
            <button type="button" className={styles.quiet} onClick={() => act("DELETE", `/api/projects/${item.id}`)}>
                Delete
            </button>
        </>
    );

    const form = editing && (
        <div className={styles.formPanel}>
            <h2 className={styles.formTitle}>
                {editing.mode === "edit" ? "Edit" : editing.mode === "accept" ? "Check and save" : "Add"}{" "}
                {editing.start.kind === "interest" ? "an interest" : "a project"}
            </h2>
            <ProjectForm start={editing.start} onSubmit={save} onCancel={() => setEditing(null)}
                         submitLabel={editing.mode === "edit" ? "Save changes" : "Save"} />
        </div>
    );

    return (
        <main id="main" className={styles.main}>
            <h1 className={styles.title}>Projects</h1>
            <p className={styles.intro}>
                What you&apos;re working on, what you&apos;re planning and what you&apos;ve done. Most calls ask for
                a project: applications will start from here.
            </p>

            <div className={styles.addRow}>
                <button type="button" className={styles.primary} onClick={() => setEditing({ mode: "add", start: EMPTY_PROJECT })}>
                    Add a project
                </button>
                <button type="button" className={styles.secondary}
                        onClick={() => setEditing({ mode: "add", start: EMPTY_INTEREST })}>
                    Add an interest
                </button>
            </div>
            {error && <p className={styles.error} role="alert">{error}</p>}
            {form}

            {data.suggestions.length > 0 && (
                <section aria-labelledby="found-heading" className={styles.found}>
                    <h2 id="found-heading" className={styles.sectionTitle}>
                        Found in your documents · {data.suggestions.length}
                    </h2>
                    <p className={styles.sectionNote}>
                        Read from your CV, statement and portfolio on our server; nothing is saved until you
                        accept it.
                    </p>
                    <ul className={styles.cards}>
                        {data.suggestions.map((s) => (
                            <Card key={s.suggestion_key} item={s}>
                                <button type="button" className={styles.primary} onClick={() => act("POST", "/api/projects", toInput(s))}>
                                    Accept
                                </button>
                                <button type="button" className={styles.secondary}
                                        onClick={() => setEditing({ mode: "accept", start: toInput(s) })}>
                                    Edit, then save
                                </button>
                                <button type="button" className={styles.quiet}
                                        onClick={() => act("POST", "/api/projects/dismiss", { key: s.suggestion_key })}>
                                    Dismiss
                                </button>
                            </Card>
                        ))}
                    </ul>
                </section>
            )}

            <section aria-labelledby="now-heading" className={styles.section}>
                <h2 id="now-heading" className={styles.sectionTitle}>Now</h2>
                {now.length > 0 ? (
                    <ul className={`${styles.cards} ${styles.cardsWide}`}>
                        {now.map((p) => <Card key={p.id} item={p}>{savedActions(p)}</Card>)}
                    </ul>
                ) : (
                    <p className={styles.empty}>Nothing in progress yet. Add the project you&apos;re working on.</p>
                )}
            </section>

            <section aria-labelledby="next-heading" className={styles.section}>
                <h2 id="next-heading" className={styles.sectionTitle}>Next</h2>
                {next.length + data.interests.length > 0 ? (
                    <ul className={styles.cards}>
                        {next.map((p) => <Card key={p.id} item={p}>{savedActions(p)}</Card>)}
                        {data.interests.map((p) => <Card key={p.id} item={p}>{savedActions(p)}</Card>)}
                    </ul>
                ) : (
                    <p className={styles.empty}>No plans yet. A planned project is often in no document: add it here.</p>
                )}
            </section>

            <section aria-labelledby="past-heading" className={styles.section}>
                <h2 id="past-heading" className={styles.sectionTitle}>Past</h2>
                {past.length > 0 ? (
                    <>
                        <ul className={styles.timeline}>
                            {pastShown.map((p) => <Card key={p.id} item={p}>{savedActions(p)}</Card>)}
                        </ul>
                        {past.length > PAST_SHOWN && (
                            <button type="button" className={styles.secondary} onClick={() => setShowAllPast(!showAllPast)}>
                                {showAllPast ? "Show fewer" : `Show all ${past.length}`}
                            </button>
                        )}
                    </>
                ) : (
                    <p className={styles.empty}>No past projects yet.</p>
                )}
            </section>
        </main>
    );
};

export default ProjectsBoard;
