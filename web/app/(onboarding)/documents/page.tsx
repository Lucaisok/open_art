import type { Metadata } from "next";
import { redirect } from "next/navigation";
import DocumentsBoard from "@/components/DocumentsBoard/DocumentsBoard";
import { apiGet } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { DocumentInfo } from "@/lib/types";

export const metadata: Metadata = { title: "Your documents · OpenArt" };

// Onboarding step 2: upload CV, statement and portfolio (all optional)
export default async function DocumentsPage() {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const documents = await apiGet<DocumentInfo[]>("/api/documents");
    return <DocumentsBoard initialDocuments={documents} />;
}
