import type { Metadata } from "next";
import { redirect } from "next/navigation";
import ProfileEditor from "@/components/ProfileEditor/ProfileEditor";
import { apiGet } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { DocumentInfo, ProfileData, ProfileOptions } from "@/lib/types";

export const metadata: Metadata = { title: "Your profile · OpenArt" };

// Onboarding step 2: the facts calls are checked against, by hand or from the documents
export default async function ProfilePage() {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const [profile, options, documents] = await Promise.all([
        apiGet<ProfileData>("/api/profile"),
        apiGet<ProfileOptions>("/api/profile/options"),
        apiGet<DocumentInfo[]>("/api/documents"),
    ]);
    return <ProfileEditor initial={profile} options={options} hasDocuments={documents.length > 0} />;
}
