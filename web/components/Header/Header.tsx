import Link from "next/link";
import { getCurrentUser } from "@/lib/session";
import NavLinks from "./NavLinks";
import styles from "./Header.module.css";

// The bar on top of every page except the login form and onboarding: the wordmark, the
// artist's pages (Log out is on the profile page). These pages are all private, so logged-out visitors only see
// the wordmark (and the page itself sends them to the login form).
const Header = async () => {
    const user = await getCurrentUser();
    return (
        <header className={styles.header}>
            <Link href={user ? "/discover" : "/"} className={styles.brand}>
                OpenArt
            </Link>
            {user && <NavLinks />}
        </header>
    );
};

export default Header;
