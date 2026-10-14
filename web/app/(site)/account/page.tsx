import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AccountPage from "@/components/Account/AccountPage";
import { getCurrentUser } from "@/lib/session";

export const metadata: Metadata = { title: "Account · OpenArt" };

// Log out, change password, what happens to the artist's data, delete the account
export default async function Account() {
    const user = await getCurrentUser();
    if (!user) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    return <AccountPage email={user.email} />;
}
