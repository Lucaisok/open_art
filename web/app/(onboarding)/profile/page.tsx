import type { Metadata } from "next";
import { redirect } from "next/navigation";
import ProfileEditor from "@/components/ProfileEditor/ProfileEditor";
import { apiGet } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { DocumentInfo, ProfileData, ProfileOptions } from "@/lib/types";

export const metadata: Metadata = { title: "Your profile · OpenArt" };

// Onboarding step 3: the facts calls are checked against, by hand or from the documents, and the
// projects found in them
export default async function ProfilePage() {
    const user = await getCurrentUser();
    if (!user) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const [profile, options, documents] = await Promise.all([
        apiGet<ProfileData>("/api/profile"),
        apiGet<ProfileOptions>("/api/profile/options"),
        apiGet<DocumentInfo[]>("/api/documents"),
    ]);
    return <ProfileEditor initial={profile} options={options} hasDocuments={documents.length > 0} email={user.email} />;
}
