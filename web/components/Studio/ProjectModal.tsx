"use client";

import { useEffect, useState } from "react";
import { postFiles, requestJson } from "@/lib/api";
import { imageUrl, IMAGE_TYPES, removeImage, thumbUrl } from "@/lib/images";
import type { ImageInfo, ProjectInput, ProjectItem } from "@/lib/types";
import { CATEGORIES } from "@/components/Projects/categories";
import Modal from "@/components/ui/Modal";
import buttons from "@/components/ui/buttons.module.css";
import ImageViewer from "./ImageViewer";
import styles from "./ProjectModal.module.css";

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const IMAGE_TYPE = /^image\/(jpeg|png|webp|gif)$/;

const WHEN = [
    { value: "current", label: "Now" },
    { value: "planned", label: "Next" },
    { value: "past", label: "Past" },
] as const;

// An image in the form: one already saved (its id), or a file picked now (sent on Save)
type FormImage = { key: string; id?: string; file?: File; url: string };

type ProjectModalProps = {
    project: ProjectItem | null;               // null: "Add a project"
    category?: "work" | "exhibition";          // a new project's starting kind (Studio's Exhibitions "+ Add")
    onClose: () => void;
    onSaved: (project: ProjectItem) => void;   // after everything (fields, images, order) is saved
    onDelete?: (project: ProjectItem) => void; // asks the parent to confirm the deletion
};

const fromSaved = (images: ImageInfo[]): FormImage[] =>
    images.map((image) => ({ key: image.id, id: image.id, url: thumbUrl(image.id) }));

// Add or edit one project (design: STUDIO.md → Project modal): where it was read from, the fields,
// and its images numbered in order (the first leads in applications), ← → to reorder, × to remove,
// "Add images". Nothing is saved until "Save project": then the fields, the removed images, the new
// images, and the order, in that order (the new images need their ids before the order is sent).
const ProjectModal = ({ project, category = "work", onClose, onSaved, onDelete }: ProjectModalProps) => {
    const [values, setValues] = useState<ProjectInput>(
        project
            ? { kind: "project", title: project.title, status: project.status, category: project.category ?? "work",
                years: project.years, medium: project.medium, summary: project.summary, venues: project.venues,
                suggestion_key: project.suggestion_key }
            : { kind: "project", status: category === "exhibition" ? "past" : "current", category, venues: [] },
    );
    const [images, setImages] = useState<FormImage[]>(() => fromSaved(project?.images ?? []));
    const [error, setError] = useState<string | null>(null);
    const [imageError, setImageError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [viewing, setViewing] = useState<number | null>(null);

    // the previews of picked files are object URLs: freed when the modal closes
    useEffect(() => () => images.forEach((i) => i.file && URL.revokeObjectURL(i.url)), []); // eslint-disable-line react-hooks/exhaustive-deps

    const set = (name: keyof ProjectInput, value: string | null) => setValues((v) => ({ ...v, [name]: value || null }));
    const move = (from: number, by: number) =>
        setImages((list) => {
            const next = list.slice();
            [next[from], next[from + by]] = [next[from + by], next[from]];
            return next;
        });
    const pick = (files: File[]) => {
        const wrong = files.find((f) => !IMAGE_TYPE.test(f.type));
        const large = files.find((f) => f.size > MAX_IMAGE_BYTES);
        if (wrong || large) {
            setImageError(wrong ? `${wrong.name} isn't a JPEG, PNG, WebP or GIF.` : `${large!.name} is larger than 10 MB.`);
            return;
        }
        setImageError(null);
        setImages((list) => list.concat(files.map((file) => ({ key: `${file.name}-${file.lastModified}-${Math.random()}`,
                                                                  file, url: URL.createObjectURL(file) }))));
    };

    const save = async () => {
        if (!values.title?.trim() && !values.summary?.trim()) {
            setError("Give it a title or a description.");
            return;
        }
        setBusy(true);
        setError(null);
        const saved = project?.id
            ? await requestJson<ProjectItem>("PUT", `/api/projects/${project.id}`, values)
            : await requestJson<ProjectItem>("POST", "/api/projects", values);
        if (!saved.ok) {
            setBusy(false);
            setError(saved.error);
            return;
        }
        const id = saved.data.id!;
        let problem: string | null = null;
        // the saved images taken out
        const kept = new Set(images.filter((i) => i.id).map((i) => i.id));
        for (const old of project?.images ?? []) {
            if (!kept.has(old.id)) problem ??= await removeImage(id, old.id);
        }
        // the new ones, one file per request (each under the server's 10 MB limit): the answer lists the
        // project's images, so the one not known before is the new one
        const ids: string[] = [];
        const known = new Set(images.filter((i) => i.id).map((i) => i.id!));
        for (const image of images) {
            if (image.id) {
                ids.push(image.id);
                continue;
            }
            const added = await postFiles<ImageInfo[]>(`/api/projects/${id}/images`, "files", [image.file!]);
            if (!added.ok) {
                problem ??= added.error;
                continue;
            }
            const fresh = added.data.find((i) => !known.has(i.id));
            if (fresh) {
                known.add(fresh.id);
                ids.push(fresh.id);
            }
        }
        if (ids.length > 1) {
            const ordered = await requestJson("PUT", `/api/projects/${id}/images`, { ids });
            if (!ordered.ok) problem ??= ordered.error;
        }
        const final = await requestJson<{ projects: ProjectItem[] }>("GET", "/api/projects");
        setBusy(false);
        const result = final.ok ? final.data.projects.find((p) => p.id === id) ?? saved.data : saved.data;
        if (problem) {
            setError(`The project is saved, but not every image: ${problem}`);
            setImages(fromSaved(result.images));
            return;
        }
        onSaved(result);
    };

    const source = project?.sources?.[0];
    const title = values.title || (project ? "this project" : "New project");
    return (
        <Modal
            title={project ? "Edit project" : "Add a project"}
            onClose={onClose}
            busy={busy}
            footer={
                <>
                    {project && onDelete && (
                        <button type="button" className={buttons.linkDanger} onClick={() => onDelete(project)} disabled={busy}>
                            Delete project
                        </button>
                    )}
                    <button type="button" className={buttons.secondary} onClick={onClose} disabled={busy}>
                        Cancel
                    </button>
                    <button type="button" className={buttons.primary} onClick={save} disabled={busy}>
                        {busy ? "Saving…" : "Save project"}
                    </button>
                </>
            }
        >
            {source && (
                <div className={buttons.quote}>
                    <span className={buttons.quoteSource}>From {source.citation}</span>“{source.quote}”
                </div>
            )}
            <label className={styles.field}>
                <span className={styles.label}>Title</span>
                <input className={styles.input} value={values.title ?? ""} maxLength={200} placeholder="e.g. Night Garden"
                       onChange={(e) => set("title", e.target.value)} />
            </label>
            <div className={styles.field}>
                <span className={styles.label} id="what-label">What it is</span>
                <div role="radiogroup" aria-labelledby="what-label" className={styles.segments}>
                    {CATEGORIES.map((c) => (
                        <button key={c.value} type="button" role="radio" aria-checked={values.category === c.value}
                                className={styles.segment} onClick={() => set("category", c.value)}>
                            {c.label}
                        </button>
                    ))}
                </div>
            </div>
            <div className={styles.field}>
                <span className={styles.label} id="when-label">When</span>
                <div role="radiogroup" aria-labelledby="when-label" className={styles.segments}>
                    {WHEN.map((w) => (
                        <button key={w.value} type="button" role="radio" aria-checked={values.status === w.value}
                                className={styles.segment} onClick={() => set("status", w.value)}>
                            {w.label}
                        </button>
                    ))}
                </div>
            </div>
            <div className={styles.row}>
                <label className={styles.field}>
                    <span className={styles.label}>Years</span>
                    <input className={styles.input} value={values.years ?? ""} maxLength={30} placeholder="2025–2026"
                           onChange={(e) => set("years", e.target.value)} />
                </label>
                <label className={styles.field}>
                    <span className={styles.label}>Medium</span>
                    <input className={styles.input} value={values.medium ?? ""} maxLength={200} placeholder="Cast glass, sound"
                           onChange={(e) => set("medium", e.target.value)} />
                </label>
            </div>
            <label className={styles.field}>
                <span className={styles.label}>Description</span>
                <textarea className={styles.textarea} rows={4} value={values.summary ?? ""} maxLength={3000}
                          onChange={(e) => set("summary", e.target.value)} />
            </label>

            <div className={styles.field}>
                <span className={styles.imagesHead}>
                    <span className={styles.label}>Images</span>
                    <span className={styles.hint}>First image leads in applications. Use the arrows to reorder.</span>
                </span>
                <ul className={styles.images}>
                    {images.map((image, n) => (
                        <li key={image.key} className={styles.image}>
                            <span className={styles.frame}>
                                <button type="button" className={`${styles.thumb} ${n === 0 ? styles.lead : ""}`}
                                        onClick={() => setViewing(n)} aria-label={`View image ${n + 1}`}>
                                    {/* eslint-disable-next-line @next/next/no-img-element */}
                                    <img src={image.url} alt="" />
                                </button>
                                <span className={styles.number} aria-hidden="true">{n + 1}</span>
                                <button type="button" className={styles.remove} aria-label={`Remove image ${n + 1}`}
                                        onClick={() => setImages((list) => list.filter((_, j) => j !== n))}>
                                    ×
                                </button>
                            </span>
                            <span className={styles.arrows}>
                                <button type="button" className={styles.arrow} disabled={n === 0} onClick={() => move(n, -1)}
                                        aria-label={`Move image ${n + 1} earlier`}>←</button>
                                <button type="button" className={styles.arrow} disabled={n === images.length - 1}
                                        onClick={() => move(n, 1)} aria-label={`Move image ${n + 1} later`}>→</button>
                            </span>
                        </li>
                    ))}
                    <li>
                        <label className={styles.add}>
                            <span aria-hidden="true" className={styles.plus}>+</span>
                            <span>Add images</span>
                            <input type="file" multiple accept={IMAGE_TYPES} className={styles.fileInput}
                                   onChange={(e) => {
                                       pick(Array.from(e.target.files ?? []));
                                       e.target.value = "";   // the same file can be picked again
                                   }} />
                        </label>
                    </li>
                </ul>
                <span className={styles.hint}>JPEG, PNG, WebP or GIF · up to 10 MB each</span>
                {imageError && <p role="alert" className={buttons.error}>{imageError}</p>}
            </div>
            {error && <p role="alert" className={buttons.error}>{error}</p>}

            {viewing !== null && (
                <ImageViewer
                    title={title}
                    start={viewing}
                    images={images.map((image, n) => ({ url: image.id ? imageUrl(image.id) : image.url,
                                                        alt: `${title}, image ${n + 1}` }))}
                    onClose={() => setViewing(null)}
                />
            )}
        </Modal>
    );
};

export default ProjectModal;
