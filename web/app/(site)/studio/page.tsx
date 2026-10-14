import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import StudioBoard from "@/components/Studio/StudioBoard";
import { apiGet } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { DocumentInfo, ProfileData, ProfileOptions, ProjectsData, SavedCalls } from "@/lib/types";

export const metadata: Metadata = { title: "Studio · OpenArt" };

// The artist's Studio (workflow.MD, "Studio restructure"): profile, saved calls, documents and
// projects, each edited in a modal. Rendered with the data in it.
export default async function StudioPage() {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const [profile, options, documents, projects] = await Promise.all([
        apiGet<ProfileData>("/api/profile"),
        apiGet<ProfileOptions>("/api/profile/options"),
        apiGet<DocumentInfo[]>("/api/documents"),
        apiGet<ProjectsData>("/api/projects"),
    ]);
    // the calls can fail on their own (the corpus): the page then shows "didn't load" with Try again
    const saved = await apiGet<SavedCalls>("/api/saved").catch(() => null);
    return (
        // useSearchParams (?edit=profile) needs a Suspense boundary
        <Suspense>
            <StudioBoard profile={profile} options={options} documents={documents} saved={saved} projects={projects} />
        </Suspense>
    );
}
