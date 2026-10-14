"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { requestJson } from "@/lib/api";
import { thumbUrl } from "@/lib/images";
import type {
    DocumentInfo, DocumentKind, ProfileData, ProfileOptions, ProjectItem, ProjectsData, SavedCall, SavedCalls,
} from "@/lib/types";
import { categoryLabel } from "@/components/Projects/categories";
import Modal from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import buttons from "@/components/ui/buttons.module.css";
import CallRow from "./CallRow";
import DocumentModal from "./DocumentModal";
import { documentMeta, SLOTS } from "./documents";
import ProfileModal from "./ProfileModal";
import ProjectModal from "./ProjectModal";
import ReviewGroups, { reviewPayload, startingPicks, type Picks } from "./ReviewGroups";
import styles from "./Studio.module.css";

const TABS = [
    { stage: "saved", label: "Saved" },
    { stage: "draft", label: "In draft" },
    { stage: "completed", label: "Completed" },
    { stage: "closed", label: "Closed" },
] as const;
type Stage = (typeof TABS)[number]["stage"];

const EMPTY: Record<Stage, string> = {
    saved: "No saved calls yet. Save calls from Discover.",
    draft: "No drafts yet. Open a saved call to start an application.",
    completed: "Nothing completed yet. A draft lands here once every text is reviewed and every item gathered.",
    closed: "No closed calls. Calls move here when their deadline passes.",
};

const ROWS_SHOWN = 6;   // past and planned projects: the first few, then "Show all"

type ModalState =
    | { kind: "profile" }
    | { kind: "document"; slot: DocumentKind }
    | { kind: "project"; project: ProjectItem | null; category?: "work" | "exhibition" }
    | { kind: "review" }
    | { kind: "confirm-call"; call: SavedCall }
    | { kind: "confirm-document"; slot: DocumentKind }
    | { kind: "confirm-project"; project: ProjectItem }
    | null;

type StudioBoardProps = {
    profile: ProfileData;
    options: ProfileOptions;
    documents: DocumentInfo[];
    saved: SavedCalls | null;      // null: the list didn't load
    projects: ProjectsData;
};

// The Studio (design: STUDIO.md → Studio): the artist at a glance, then three columns — documents,
// their calls (saved / in draft / completed / closed), their projects — each editable through a
// modal. Every change is saved by its own modal's button, then the column is read again from the
// server, so what is shown is what is stored. /studio?edit=profile opens the profile modal (links
// from Discover and the call page), ?edit=cv|statement|portfolio a document's.
const StudioBoard = ({ profile: startProfile, options, documents: startDocuments, saved: startSaved,
                       projects: startProjects }: StudioBoardProps) => {
    const router = useRouter();
    const params = useSearchParams();
    const toast = useToast();
    const [profile, setProfile] = useState(startProfile);
    const [documents, setDocuments] = useState(startDocuments);
    const [saved, setSaved] = useState(startSaved);
    const [projects, setProjects] = useState(startProjects);
    const [tab, setTab] = useState<Stage>(() => {
        const first = TABS.find((t) => (startSaved?.counts[t.stage] ?? 0) > 0);
        return first?.stage ?? "saved";
    });
    const [modal, setModal] = useState<ModalState>(() => {
        const edit = params.get("edit");
        if (edit === "profile") return { kind: "profile" };
        if (edit === "cv" || edit === "statement" || edit === "portfolio") return { kind: "document", slot: edit };
        return null;
    });
    const [showAll, setShowAll] = useState(false);
    const [picks, setPicks] = useState<Picks>(() => startingPicks(startProjects.suggestions));
    const [busy, setBusy] = useState(false);

    const close = () => {
        setModal(null);
        if (params.get("edit")) router.replace("/studio", { scroll: false });   // a reload doesn't reopen it
    };

    const reloadSaved = useCallback(async () => {
        const fresh = await requestJson<SavedCalls>("GET", "/api/saved");
        setSaved(fresh.ok ? fresh.data : null);
    }, []);
    const reloadProjects = useCallback(async () => {
        const fresh = await requestJson<ProjectsData>("GET", "/api/projects");
        if (fresh.ok) setProjects(fresh.data);
    }, []);
    const reloadProfile = useCallback(async () => {
        const fresh = await requestJson<ProfileData>("GET", "/api/profile");
        if (fresh.ok) setProfile(fresh.data);
    }, []);
    const reloadDocuments = useCallback(async () => {
        const fresh = await requestJson<DocumentInfo[]>("GET", "/api/documents");
        if (fresh.ok) setDocuments(fresh.data);
    }, []);

    // a PDF's images are read in the background after its upload: ask again until they are, then the
    // projects found with them (and the profile values) are fresh too
    const reading = documents.some((d) => d.reading_images);
    useEffect(() => {
        if (!reading) return;
        const timer = window.setTimeout(async () => {
            await reloadDocuments();
            await Promise.all([reloadProjects(), reloadProfile()]);
        }, 4000);
        return () => window.clearTimeout(timer);
    }, [reading, documents, reloadDocuments, reloadProjects, reloadProfile]);

    // -- the artist at a glance -------------------------------------------------------------------------
    const v = profile.values;
    const country = options.countries.find((c) => c.code === v.residence_country)?.name;
    const place = [v.residence_city, country].filter(Boolean).join(", ");
    const disciplines = (v.disciplines ?? []).join(", ");
    const missing = [
        !v.name && "your name",
        !disciplines && "disciplines",
        !v.residence_country && "country of residence",
    ].filter(Boolean) as string[];
    const missingText = missing.length > 1 ? `${missing.slice(0, -1).join(", ")} and ${missing.at(-1)}` : missing[0];
    const newDetails = (profile.suggestions?.items.length ?? 0) > 0;

    // -- projects ---------------------------------------------------------------------------------------
    const isShow = (p: ProjectItem) => p.category === "exhibition";
    const current = projects.projects.filter((p) => !isShow(p) && p.status === "current");
    const others = projects.projects.filter((p) => !isShow(p) && p.status !== "current");
    const shows = projects.projects.filter(isShow);
    const foundCount = projects.suggestions.length;

    // -- actions ----------------------------------------------------------------------------------------
    const removeCall = async (call: SavedCall) => {
        setBusy(true);
        const result = await requestJson("DELETE", `/api/saved/${encodeURIComponent(call.id)}`);
        setBusy(false);
        close();
        if (result.ok) toast("Removed from your calls");
        await reloadSaved();
    };
    const removeDocument = async (slot: DocumentKind) => {
        setBusy(true);
        const result = await requestJson("DELETE", `/api/documents/${slot}`);
        setBusy(false);
        close();
        if (result.ok) toast(`${SLOTS.find((s) => s.kind === slot)!.label} removed`);
        await Promise.all([reloadDocuments(), reloadProjects(), reloadProfile(), reloadSaved()]);
    };
    const deleteProject = async (project: ProjectItem) => {
        setBusy(true);
        const result = await requestJson("DELETE", `/api/projects/${project.id}`);
        setBusy(false);
        close();
        if (result.ok) toast("Project deleted");
        await Promise.all([reloadProjects(), reloadSaved()]);
    };
    const saveReview = async () => {
        setBusy(true);
        const result = await requestJson<ProjectsData>("POST", "/api/projects/review", reviewPayload(projects.suggestions, picks));
        setBusy(false);
        if (result.ok) {
            setProjects(result.data);
            close();
            toast("Projects saved");
            await reloadSaved();   // the current projects rank the calls
        }
    };

    const slotLabel = (slot: DocumentKind) => SLOTS.find((s) => s.kind === slot)!.label;
    const calls = saved?.calls.filter((c) => c.stage === tab) ?? [];
    const shown = showAll ? others : others.slice(0, ROWS_SHOWN);

    return (
        <main id="main" className={styles.main}>
            <section aria-labelledby="h-artist" className={styles.artist}>
                <span className={styles.eyebrow}>Studio</span>
                <h1 id="h-artist" className={styles.name}>{v.name || "Your studio"}</h1>
                <div className={styles.artistFacts}>
                    <span className={disciplines ? "" : styles.unset}>{disciplines || "Disciplines not set"}</span>
                    <span className={place ? "" : styles.unset}>{place || "Based in: not set"}</span>
                    <button type="button" className={styles.edit} onClick={() => setModal({ kind: "profile" })}>Edit</button>
                </div>
                {(missing.length > 0 || newDetails) && (
                    <p className={styles.incomplete}>
                        {newDetails
                            ? "Your documents have new details for your profile. "
                            : `Your profile is missing ${missingText}. Calls match better with a full profile. `}
                        <button type="button" className={buttons.link} onClick={() => setModal({ kind: "profile" })}>
                            {newDetails ? "Review them" : "Complete your profile"}
                        </button>
                    </p>
                )}
            </section>

            <div className={styles.grid}>
                <section aria-labelledby="h-calls" className={styles.calls}>
                    <div className={styles.sectionHead}>
                        <h2 id="h-calls" className={styles.sectionTitle}>My calls</h2>
                        <Link href="/discover" className={styles.headLink}>Find more calls →</Link>
                    </div>
                    <div role="tablist" aria-label="Call status" className={styles.tabs}>
                        {TABS.map((t) => (
                            <button key={t.stage} type="button" role="tab" aria-selected={tab === t.stage}
                                    aria-controls="calls-panel" className={styles.tab} onClick={() => setTab(t.stage)}>
                                <span>{t.label}</span>
                                <span className={styles.tabCount}>{saved ? saved.counts[t.stage] ?? 0 : "–"}</span>
                            </button>
                        ))}
                    </div>
                    <div id="calls-panel" role="tabpanel" className={styles.scroll}>
                        {saved === null ? (
                            <p role="alert" className={styles.loadError}>
                                Your calls didn&apos;t load. Check your connection and{" "}
                                <button type="button" className={buttons.link} onClick={reloadSaved}>try again</button>.
                            </p>
                        ) : calls.length === 0 ? (
                            <div className={styles.empty}>
                                <p className={styles.emptyText}>{EMPTY[tab]}</p>
                                {tab === "saved" && <Link href="/discover" className={buttons.dark}>Go to Discover →</Link>}
                            </div>
                        ) : (
                            <ul className={styles.callList}>
                                {calls.map((c) => (
                                    <CallRow key={c.id} call={c} onRemove={(call) => setModal({ kind: "confirm-call", call })} />
                                ))}
                            </ul>
                        )}
                    </div>
                </section>

                <section aria-labelledby="h-docs" className={styles.docs}>
                    <div className={styles.sectionHead}>
                        <h2 id="h-docs" className={styles.sectionTitle}>Documents</h2>
                    </div>
                    <dl className={styles.docList}>
                        {SLOTS.map((slot) => {
                            const d = documents.find((x) => x.kind === slot.kind);
                            return (
                                <div key={slot.kind} className={styles.doc}>
                                    <dt className={styles.docLabel}>{slot.label}</dt>
                                    <dd className={styles.docBody}>
                                        {d ? (
                                            <>
                                                <span className={styles.docName}>{d.file_name}</span>
                                                <span className={styles.docMeta}>{documentMeta(d)}</span>
                                                {d.reading_images && (
                                                    <span className={styles.busy} aria-live="polite">
                                                        <span>Reading images…</span>
                                                        <span className={styles.busyTrack}><span className={styles.busyBar} /></span>
                                                    </span>
                                                )}
                                                <span className={styles.docActions}>
                                                    <button type="button" className={buttons.link}
                                                            onClick={() => setModal({ kind: "document", slot: slot.kind })}>Replace</button>
                                                    <button type="button" className={buttons.link}
                                                            onClick={() => setModal({ kind: "confirm-document", slot: slot.kind })}>Remove</button>
                                                </span>
                                            </>
                                        ) : (
                                            <>
                                                <span className={styles.docEmpty}>Not uploaded · {slot.hint}</span>
                                                <button type="button" className={`${buttons.link} ${styles.upload}`}
                                                        onClick={() => setModal({ kind: "document", slot: slot.kind })}>Upload</button>
                                            </>
                                        )}
                                    </dd>
                                </div>
                            );
                        })}
                    </dl>
                    <p className={styles.note}>
                        One file can hold everything. If your CV includes your portfolio, upload it once: OpenArt reads both.
                    </p>
                </section>

                <section aria-labelledby="h-projects" className={styles.projects}>
                    <div className={styles.sectionHead}>
                        <h2 id="h-projects" className={styles.sectionTitle}>Projects</h2>
                        <button type="button" className={buttons.link} onClick={() => setModal({ kind: "project", project: null })}>
                            + Add a project
                        </button>
                    </div>
                    <div className={styles.projectsScroll}>
                        {foundCount > 0 && (
                            <p className={styles.found}>
                                We found {foundCount} {foundCount === 1 ? "project" : "projects"} in your documents.{" "}
                                <button type="button" className={buttons.link} onClick={() => {
                                    setPicks(startingPicks(projects.suggestions));
                                    setModal({ kind: "review" });
                                }}>Review</button>
                            </p>
                        )}
                        {current.length + others.length === 0 ? (
                            <div className={styles.projectsEmpty}>
                                <span>No projects yet. Add what you&apos;re working on: calls are matched to your current projects first.</span>
                                <button type="button" className={`${buttons.dark} ${buttons.small}`}
                                        onClick={() => setModal({ kind: "project", project: null })}>Add a project</button>
                            </div>
                        ) : (
                            <div className={styles.projectStack}>
                                {current.length > 0 && (
                                    <div className={styles.currentList}>
                                        {current.map((p) => (
                                            <button key={p.id} type="button" className={styles.currentProject}
                                                    onClick={() => setModal({ kind: "project", project: p })}>
                                                {p.images.length > 0 && (
                                                    <span className={styles.strip}>
                                                        {p.images.slice(0, 4).map((image) => (
                                                            // eslint-disable-next-line @next/next/no-img-element
                                                            <img key={image.id} src={thumbUrl(image.id)} alt="" loading="lazy" />
                                                        ))}
                                                    </span>
                                                )}
                                                <span className={styles.projectText}>
                                                    <span className={styles.projectKind}>
                                                        <span aria-hidden="true" className={`${styles.marker} ${styles.markerOk}`} />
                                                        {categoryLabel(p.category) ?? "Work"} · Current project
                                                    </span>
                                                    <span className={styles.projectTitle}>{p.title ?? "Untitled project"}</span>
                                                    <span className={styles.projectMeta}>{[p.years, p.medium].filter(Boolean).join(" · ")}</span>
                                                </span>
                                            </button>
                                        ))}
                                    </div>
                                )}
                                {others.length > 0 && (
                                    <div>
                                        <ol className={styles.rows}>
                                            {shown.map((p) => (
                                                <li key={p.id}>
                                                    <ProjectRowButton project={p} onOpen={() => setModal({ kind: "project", project: p })} />
                                                </li>
                                            ))}
                                        </ol>
                                        {others.length > ROWS_SHOWN && (
                                            <button type="button" className={buttons.link} aria-expanded={showAll}
                                                    onClick={() => setShowAll(!showAll)}>
                                                {showAll ? "Show fewer" : `Show all ${others.length}`}
                                            </button>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                    <div className={`${styles.sectionHead} ${styles.showsHead}`}>
                        <h2 id="h-shows" className={styles.sectionTitle}>Exhibitions</h2>
                        <button type="button" className={buttons.link}
                                onClick={() => setModal({ kind: "project", project: null, category: "exhibition" })}>+ Add</button>
                    </div>
                    <div className={styles.showsScroll}>
                        {shows.length === 0 ? (
                            <p className={styles.showsEmpty}>No exhibitions or screenings yet.</p>
                        ) : (
                            <ol className={styles.rows}>
                                {shows.map((p) => (
                                    <li key={p.id}>
                                        <ProjectRowButton project={p} onOpen={() => setModal({ kind: "project", project: p })} />
                                    </li>
                                ))}
                            </ol>
                        )}
                    </div>
                </section>
            </div>

            {modal?.kind === "profile" && (
                <ProfileModal initial={profile} options={options} onClose={close}
                              onSaved={async (fresh) => {
                                  setProfile(fresh);
                                  close();
                                  toast("Profile saved");
                                  await reloadSaved();   // verdicts use the saved profile
                              }} />
            )}
            {modal?.kind === "document" && (
                <DocumentModal kind={modal.slot} label={slotLabel(modal.slot)}
                               current={documents.find((d) => d.kind === modal.slot) ?? null}
                               onClose={close}
                               onRemove={() => setModal({ kind: "confirm-document", slot: modal.slot })}
                               onUploaded={async () => {
                                   close();
                                   toast(`${slotLabel(modal.slot)} uploaded`);
                                   await Promise.all([reloadDocuments(), reloadProfile(), reloadProjects(), reloadSaved()]);
                               }} />
            )}
            {modal?.kind === "project" && (
                <ProjectModal project={modal.project} category={modal.category} onClose={close}
                              onDelete={(project) => setModal({ kind: "confirm-project", project })}
                              onSaved={async () => {
                                  close();
                                  toast("Project saved");
                                  await Promise.all([reloadProjects(), reloadSaved()]);
                              }} />
            )}
            {modal?.kind === "review" && (
                <Modal title="Projects found in your documents" onClose={close} busy={busy}
                       footer={
                           <>
                               <button type="button" className={buttons.secondary} onClick={close} disabled={busy}>Cancel</button>
                               <button type="button" className={buttons.primary} onClick={saveReview} disabled={busy}>
                                   {busy ? "Saving…" : "Save projects"}
                               </button>
                           </>
                       }>
                    <p className={styles.modalLead}>
                        Ticked ones are saved to your projects; unticked ones won&apos;t be suggested again.
                    </p>
                    <ReviewGroups suggestions={projects.suggestions} picks={picks} onChange={setPicks} />
                </Modal>
            )}
            {modal?.kind === "confirm-call" && (
                <Modal size="sm" title="Remove from saved?" onClose={close} busy={busy}
                       footer={
                           <>
                               <button type="button" className={buttons.secondary} onClick={close} disabled={busy}>Cancel</button>
                               <button type="button" className={buttons.dark} onClick={() => removeCall(modal.call)} disabled={busy}>Remove</button>
                           </>
                       }>
                    <p className={styles.confirm}>
                        {modal.call.title} will be removed from your calls{modal.call.progress ? ", with its draft" : ""}. You can save
                        it again from Discover.
                    </p>
                </Modal>
            )}
            {modal?.kind === "confirm-document" && (() => {
                const d = documents.find((x) => x.kind === modal.slot);
                const noun = modal.slot === "cv" ? "CV" : slotLabel(modal.slot).toLowerCase();
                return (
                    <Modal size="sm" title={`Remove your ${noun}?`} onClose={close} busy={busy}
                           footer={
                               <>
                                   <button type="button" className={buttons.secondary} onClick={close} disabled={busy}>Cancel</button>
                                   <button type="button" className={buttons.danger} onClick={() => removeDocument(modal.slot)}
                                           disabled={busy}>Remove</button>
                               </>
                           }>
                        <p className={styles.confirm}>
                            {d?.file_name ?? "The file"} will be deleted from OpenArt. Calls that ask for a {noun} will show it as missing.
                        </p>
                    </Modal>
                );
            })()}
            {modal?.kind === "confirm-project" && (
                <Modal size="sm" title={`Delete ${modal.project.title ?? "this project"}?`} onClose={close} busy={busy}
                       footer={
                           <>
                               <button type="button" className={buttons.secondary} onClick={close} disabled={busy}>Cancel</button>
                               <button type="button" className={buttons.danger} onClick={() => deleteProject(modal.project)}
                                       disabled={busy}>Delete project</button>
                           </>
                       }>
                    <p className={styles.confirm}>
                        The project
                        {modal.project.images.length > 0
                            ? ` and its ${modal.project.images.length} ${modal.project.images.length === 1 ? "image" : "images"}`
                            : ""}{" "}
                        will be deleted. This can&apos;t be undone.
                    </p>
                </Modal>
            )}
        </main>
    );
};

// A project as a row: a 44 px image (or a grey square), its title, "years · kind"
const ProjectRowButton = ({ project, onOpen }: { project: ProjectItem; onOpen: () => void }) => {
    const first = project.images[0];
    const meta = [project.years, project.status === "planned" ? "Next" : null,
                  project.category === "exhibition" ? project.medium : categoryLabel(project.category)]
        .filter(Boolean).join(" · ");
    return (
        <button type="button" className={styles.row} onClick={onOpen}>
            {first ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={thumbUrl(first.id)} alt="" className={styles.rowThumb} loading="lazy" />
            ) : (
                <span className={styles.rowThumb} aria-hidden="true" />
            )}
            <span className={styles.rowText}>
                <span className={styles.rowTitle}>{project.title ?? "Untitled project"}</span>
                {meta && <span className={styles.rowMeta}>{meta}</span>}
            </span>
        </button>
    );
};

export default StudioBoard;
