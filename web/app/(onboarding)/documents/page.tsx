import type { Metadata } from "next";
import { redirect } from "next/navigation";
import DocumentsBoard from "@/components/DocumentsBoard/DocumentsBoard";
import { apiGet } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { DocumentInfo, ProfileData } from "@/lib/types";

export const metadata: Metadata = { title: "Your documents · OpenArt" };

// Onboarding step 2: upload CV, statement and portfolio (all optional)
export default async function DocumentsPage() {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const [documents, profile] = await Promise.all([
        apiGet<DocumentInfo[]>("/api/documents"),
        apiGet<ProfileData>("/api/profile"),
    ]);
    // onboarding until the profile is first saved (the same rule as the header, app/(onboarding)/layout.tsx)
    return <DocumentsBoard initialDocuments={documents} onboarding={profile.updated_at === null} />;
}
