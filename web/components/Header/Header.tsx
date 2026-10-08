import Link from "next/link";
import { getCurrentUser } from "@/lib/session";
import LogoutButton from "./LogoutButton";
import styles from "./Header.module.css";

// The bar on top of every page except the login form: the wordmark, the artist's pages,
// "Log out". These pages are all private, so logged-out visitors only see the wordmark
// (and the page itself sends them to the login form).
const Header = async () => {
    const user = await getCurrentUser();
    return (
        <header className={styles.header}>
            <Link href="/" className={styles.brand}>
                OpenArt
            </Link>
            {user && (
                <nav aria-label="Main">
                    <ul className={styles.links}>
                        <li>
                            <Link href="/documents" className={styles.link}>
                                Documents
                            </Link>
                        </li>
                        <li>
                            <Link href="/profile" className={styles.link}>
                                Profile
                            </Link>
                        </li>
                        <li>
                            <Link href="/account" className={styles.link} title={user.email}>
                                Account
                            </Link>
                        </li>
                        <li>
                            <LogoutButton className={styles.logout} />
                        </li>
                    </ul>
                </nav>
            )}
        </header>
    );
};

export default Header;
