import Link from "next/link";
import { getCurrentUser } from "@/lib/session";
import LogoutButton from "./LogoutButton";
import styles from "./Header.module.css";

// The bar at the top of every page: the logged-in email and "Log out", or the links to get in
const Header = async () => {
    const user = await getCurrentUser();
    return (
        <header className={styles.header}>
            <Link href="/" className={styles.brand}>
                OpenArt
            </Link>
            <nav aria-label="Account">
                <ul className={styles.links}>
                    {user ? (
                        <>
                            <li>
                                <Link href="/account" className={styles.link}>
                                    {user.email}
                                </Link>
                            </li>
                            <li>
                                <LogoutButton />
                            </li>
                        </>
                    ) : (
                        <>
                            <li>
                                <Link href="/login" className={styles.link}>
                                    Log in
                                </Link>
                            </li>
                            <li>
                                <Link href="/signup" className={styles.link}>
                                    Sign up
                                </Link>
                            </li>
                        </>
                    )}
                </ul>
            </nav>
        </header>
    );
};

export default Header;
