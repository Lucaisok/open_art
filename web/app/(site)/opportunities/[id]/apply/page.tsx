import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import ApplyWorkspace from "@/components/Apply/ApplyWorkspace";
import { apiGetOrNull } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { ApplicationData } from "@/lib/types";

type ApplyPageProps = { params: Promise<{ id: string }> };

export const metadata: Metadata = { title: "Draft an application · OpenArt" };

// The application page (workflow.MD, "Step 6"): what the call needs, the assistant and the drafts.
// Rendered with the artist's application in it (api/applications.py).
export default async function ApplyPage({ params }: ApplyPageProps) {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const id = (await params).id;
    const data = await apiGetOrNull<ApplicationData>(`/api/applications/${encodeURIComponent(id)}`);
    if (!data) {
        notFound();
    }
    return <ApplyWorkspace initial={data} />;
}
