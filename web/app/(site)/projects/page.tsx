import type { Metadata } from "next";
import { redirect } from "next/navigation";
import ProjectsBoard from "@/components/Projects/ProjectsBoard";
import { apiGet } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { ProjectsData } from "@/lib/types";

export const metadata: Metadata = { title: "Projects · OpenArt" };

// The artist's projects (past, current, planned) and interests, plus what the rules read from
// their documents, to accept or dismiss (workflow.MD, "Projects page"). Rendered with the data in it.
export default async function ProjectsPage() {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const data = await apiGet<ProjectsData>("/api/projects");
    return <ProjectsBoard initial={data} />;
}
