"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { requestJson, sendJson } from "@/lib/api";
import { forgetSearch } from "@/lib/discover";
import type { DocumentInfo, ProjectsData } from "@/lib/types";
import ProjectModal from "@/components/Studio/ProjectModal";
import ReviewGroups, { keptCount, reviewPayload, startingPicks, type Picks } from "@/components/Studio/ReviewGroups";
import { useToast } from "@/components/ui/Toast";
import SetupSteps from "@/components/Onboarding/SetupSteps";
import onboarding from "@/components/Onboarding/Onboarding.module.css";
import buttons from "@/components/ui/buttons.module.css";
import styles from "./OnboardingProjects.module.css";

type OnboardingProjectsProps = {
    initial: ProjectsData;
    reading: boolean;      // a PDF's images are still being read: ask again until they are
};

// Onboarding step 3 (design: STUDIO.md → Onboarding step 3). The projects found in the documents,
// all kept to start with; the artist unticks what shouldn't be used and marks what is current.
// "Continue to Discover" keeps the ticked ones (POST /api/projects/review), dismisses the others,
// and finishes the onboarding (POST /api/account/onboarded): from then on the app is Discover,
// Studio and Account. A project typed in with "+ Add a project" is saved at once.
const OnboardingProjects = ({ initial, reading: startReading }: OnboardingProjectsProps) => {
    const router = useRouter();
    const toast = useToast();
    const [data, setData] = useState(initial);
    const [picks, setPicks] = useState<Picks>(() => startingPicks(initial.suggestions));
    const [reading, setReading] = useState(startReading);
    const [adding, setAdding] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // the images of a PDF just uploaded arrive in the background: ask again every few seconds
    useEffect(() => {
        if (!reading) return;
        const timer = window.setTimeout(async () => {
            const [projects, documents] = await Promise.all([
                requestJson<ProjectsData>("GET", "/api/projects"),
                requestJson<DocumentInfo[]>("GET", "/api/documents"),
            ]);
            if (projects.ok) setData(projects.data);
            if (documents.ok) setReading(documents.data.some((d) => d.reading_images));
        }, 4000);
        return () => window.clearTimeout(timer);
    }, [reading, data]);

    const finish = async () => {
        setBusy(true);
        setError(null);
        const review = await requestJson("POST", "/api/projects/review", reviewPayload(data.suggestions, picks));
        const done = review.ok ? await sendJson("POST", "/api/account/onboarded") : review;
        if (!done.ok) {
            setBusy(false);
            setError(done.error);
            return;
        }
        forgetSearch();
        router.push("/discover");
        router.refresh();
    };

    const empty = data.suggestions.length === 0;
    const added = data.projects.filter((p) => !p.from_documents);
    return (
        <main id="main" className={onboarding.main}>
            <SetupSteps current={2} />

            <div className={styles.intro}>
                <div className={`${onboarding.intro} ${styles.introText}`}>
                    <h1 className={onboarding.title}>Your projects</h1>
                    <p className={onboarding.lead}>
                        {empty
                            ? "Tell OpenArt what you're making so calls can be matched to it."
                            : "We found these in your documents. Untick anything that shouldn't be used, and mark what you're working on now."}
                    </p>
                </div>
                <button type="button" className={buttons.link} onClick={() => setAdding(true)}>+ Add a project</button>
            </div>

            {reading && (
                <p className={styles.reading} role="status">
                    Reading the images in your documents… they&apos;ll appear on the projects in a few seconds.
                </p>
            )}
            {added.length > 0 && (
                <p className={styles.added}>
                    Added by you: {added.map((p) => p.title ?? "Untitled project").join(", ")}
                </p>
            )}

            {empty ? (
                <div className={styles.empty}>
                    <p className={styles.emptyText}>
                        Nothing found in your documents. Add what you&apos;re working on: calls are matched to your
                        current projects first.
                    </p>
                    <button type="button" className={buttons.dark} onClick={() => setAdding(true)}>Add a project →</button>
                </div>
            ) : (
                <div className={styles.groups}>
                    <ReviewGroups suggestions={data.suggestions} picks={picks} onChange={setPicks} />
                </div>
            )}

            <div className={onboarding.bar}>
                <div className={onboarding.barInner}>
                    <Link href="/profile" className={`${buttons.secondary} ${onboarding.back}`}>← Back</Link>
                    <span className={onboarding.status} aria-live="polite">
                        {error ?? (empty ? "" : `${keptCount(data.suggestions, picks)} kept`)}
                    </span>
                    <button type="button" className={`${buttons.primary} ${onboarding.next}`} onClick={finish} disabled={busy}>
                        <span className={styles.continueLong}>{busy ? "Saving…" : "Continue to Discover →"}</span>
                        <span className={styles.continueShort}>{busy ? "Saving…" : "Continue →"}</span>
                    </button>
                </div>
            </div>

            {adding && (
                <ProjectModal
                    project={null}
                    onClose={() => setAdding(false)}
                    onSaved={async () => {
                        setAdding(false);
                        toast("Project saved");
                        const fresh = await requestJson<ProjectsData>("GET", "/api/projects");
                        if (fresh.ok) setData(fresh.data);
                    }}
                />
            )}
        </main>
    );
};

export default OnboardingProjects;
