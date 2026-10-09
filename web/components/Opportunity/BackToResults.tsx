"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";
import { LAST_SEARCH_KEY, SCROLL_KEY } from "@/lib/discover";
import styles from "./OpportunityView.module.css";

// "← Back to results": to the Discover search the artist came from (its address is kept in this
// tab's sessionStorage), where Discover also restores the scroll position. A link, since it
// navigates; with no saved search (opened from a bookmark) it leads to a fresh Discover.
const BackToResults = () => {
    const router = useRouter();

    const goBack = (event: MouseEvent<HTMLAnchorElement>) => {
        let last: string | null = null;
        let scrollSaved = false;
        try {
            last = sessionStorage.getItem(LAST_SEARCH_KEY);
            scrollSaved = sessionStorage.getItem(SCROLL_KEY) !== null;
        } catch {
            // storage blocked: the plain link's fresh Discover
        }
        if (last && !event.metaKey && !event.ctrlKey) {   // a new tab keeps the plain link
            event.preventDefault();
            // with a saved position Discover scrolls there itself: Next must not jump to the top after it
            router.push(`/discover${last}`, { scroll: !scrollSaved });
        }
    };

    return (
        <Link href="/discover" className={styles.back} onClick={goBack}>
            ← Back to results
        </Link>
    );
};

export default BackToResults;
