import Link from "next/link";
import { getCurrentUser } from "@/lib/session";
import styles from "./page.module.css";

export default async function Home() {
    const user = await getCurrentUser();

    return (
        <main id="main" className={styles.main}>
            <h1 className={styles.title}>OpenArt</h1>
            <p className={styles.lead}>
                Find open calls for artists, check your eligibility and prepare your application.
            </p>
            <div className={styles.actions}>
                {user ? (
                    <Link href="/account" className={styles.primary}>
                        Go to your account
                    </Link>
                ) : (
                    <>
                        <Link href="/signup" className={styles.primary}>
                            Create an account
                        </Link>
                        <Link href="/login" className={styles.secondary}>
                            Log in
                        </Link>
                    </>
                )}
            </div>
        </main>
    );
}
