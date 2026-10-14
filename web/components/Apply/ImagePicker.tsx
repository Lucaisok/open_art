"use client";

import Link from "next/link";
import { useState } from "react";
import { thumbUrl } from "@/lib/images";
import type { ApplicationItem, ProjectImages } from "@/lib/types";
import Modal from "@/components/ui/Modal";
import buttons from "@/components/ui/buttons.module.css";
import styles from "./Apply.module.css";

type ImagePickerProps = {
    item: ApplicationItem;               // an item asking for images of the work
    choices: ProjectImages[];            // the saved projects' images, closest to the call first
    onClose: () => void;
    onUse: (ids: string[]) => void;
};

// Choose images (design: APPLICATION.md → Image picker): the saved projects' images, grouped by
// project. Ticked images get a lime number, their order in the downloaded folder (01, 02…).
const ImagePicker = ({ item, choices, onClose, onUse }: ImagePickerProps) => {
    const [picked, setPicked] = useState<string[]>(() => item.images.map((i) => i.id));
    const toggle = (id: string) => setPicked((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]));
    const label = picked.length ? `Use ${picked.length} ${picked.length === 1 ? "image" : "images"}` : item.images.length ? "Use none" : "Use 0 images";
    return (
        <Modal
            size="lg"
            title="Choose images"
            subtitle={[item.title, item.limit].filter(Boolean).join(" · ")}
            onClose={onClose}
            footer={
                <>
                    <span className={styles.pickerCount}>{picked.length} selected</span>
                    <button type="button" className={buttons.secondary} onClick={onClose}>Cancel</button>
                    {/* none picked: only useful to clear a choice made before */}
                    <button type="button" className={buttons.primary} onClick={() => onUse(picked)}
                            disabled={picked.length === 0 && item.images.length === 0}>
                        {label}
                    </button>
                </>
            }
        >
            {choices.length === 0 ? (
                <div className={styles.pickerEmpty}>
                    <p>None of your projects has images yet.</p>
                    <Link href="/studio">Add images to a project →</Link>
                </div>
            ) : (
                <>
                    <p className={styles.muted}>Numbers show the order of the images in the downloaded folder. Tick in the order you want them.</p>
                    {choices.map((project) => (
                        <div key={project.project_id} className={styles.pickerGroup}>
                            <span className={styles.pickerGroupHead}>
                                <span className={styles.pickerGroupTitle}>{project.title}</span>
                                <span className={styles.muted}>
                                    {[project.years, `${project.images.length} ${project.images.length === 1 ? "image" : "images"}`].filter(Boolean).join(" · ")}
                                </span>
                            </span>
                            <div className={styles.pickerGrid}>
                                {project.images.map((image, n) => {
                                    const order = picked.indexOf(image.id) + 1;
                                    return (
                                        <button key={image.id} type="button" role="checkbox" aria-checked={order > 0}
                                                aria-label={`${project.title}, image ${n + 1}`}
                                                className={`${styles.pickerImage} ${order > 0 ? styles.pickerImageOn : ""}`}
                                                onClick={() => toggle(image.id)}>
                                            {/* eslint-disable-next-line @next/next/no-img-element */}
                                            <img src={thumbUrl(image.id)} alt="" loading="lazy" />
                                            {order > 0 ? (
                                                <span className={styles.pickerNumber}>{String(order).padStart(2, "0")}</span>
                                            ) : (
                                                <span className={styles.pickerBox} aria-hidden="true" />
                                            )}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </>
            )}
        </Modal>
    );
};

export default ImagePicker;
