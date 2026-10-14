import { redirect } from "next/navigation";
import OnboardingHeader from "@/components/OnboardingHeader/OnboardingHeader";
import { getCurrentUser } from "@/lib/session";
import styles from "./layout.module.css";

// The onboarding: Documents -> Profile -> Projects. Once the artist finished it ("Continue to
// Discover" on Projects) these pages are gone from the app: documents, profile and projects are
// edited in the Studio, so they send there. Each page brings its own footer bar.
export default async function OnboardingLayout({ children }: Readonly<{ children: React.ReactNode }>) {
    const user = await getCurrentUser();
    if (user?.onboarded_at) {
        redirect("/studio");
    }
    return (
        <div className={styles.shell}>
            <OnboardingHeader />
            {children}
        </div>
    );
}
