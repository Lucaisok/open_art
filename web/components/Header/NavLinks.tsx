"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./Header.module.css";

// After the onboarding the app is three pages (workflow.MD, "Studio restructure"): Documents,
// Profile and Projects were onboarding steps; they are edited in the Studio from then on.
const LINKS = [
    { label: "Discover", href: "/discover", also: "/opportunities" },   // a call's page belongs to Discover
    { label: "Studio", href: "/studio" },
    { label: "Account", href: "/account" },
];

// The artist's pages as pills; the current one is filled (design: STUDIO.md → App structure).
// A client component only to know the current page.
const NavLinks = () => {
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
                            >
                                {link.label}
                            </Link>
                        </li>
                    );
                })}
            </ul>
        </nav>
    );
};

export default NavLinks;
