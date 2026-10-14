import type { Metadata } from "next";
import { redirect } from "next/navigation";
import OnboardingProjects from "@/components/OnboardingProjects/OnboardingProjects";
import { apiGet } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { DocumentInfo, ProjectsData } from "@/lib/types";

export const metadata: Metadata = { title: "Your projects · OpenArt" };

// Onboarding step 3 (design: STUDIO.md → Onboarding step 3): the projects found in the documents,
// to keep or not and to mark as current; "Continue to Discover" finishes the onboarding
export default async function ProjectsStepPage() {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const [projects, documents] = await Promise.all([
        apiGet<ProjectsData>("/api/projects"),
        apiGet<DocumentInfo[]>("/api/documents"),
    ]);
    return <OnboardingProjects initial={projects} reading={documents.some((d) => d.reading_images)} />;
}
