"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import LogoutButton from "./LogoutButton";
import styles from "./Header.module.css";

const LINKS = [
    { label: "Discover", href: "/discover", also: "/opportunities" },   // a call's page belongs to Discover
    { label: "Documents", href: "/documents" },
    { label: "Profile", href: "/profile" },
    { label: "Account", href: "/account" },
];

// The artist's pages as pills; the current one is filled (design: DISCOVER.md → Global header).
// A client component only to know the current page.
const NavLinks = ({ email }: { email: string }) => {
    const pathname = usePathname();
    return (
        <nav aria-label="Main">
            <ul className={styles.links}>
                {LINKS.map((link) => {
                    const current = pathname.startsWith(link.href) || (link.also && pathname.startsWith(link.also));
                    return (
                        <li key={link.href}>
                            <Link
                                href={link.href}
                                className={styles.link}
                                aria-current={current ? "page" : undefined}
                                title={link.href === "/account" ? email : undefined}
                            >
                                {link.label}
                            </Link>
                        </li>
                    );
                })}
                <li>
                    <LogoutButton className={styles.logout} />
                </li>
            </ul>
        </nav>
    );
};

export default NavLinks;
