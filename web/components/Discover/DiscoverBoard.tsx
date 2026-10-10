"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { requestJson } from "@/lib/api";
import {
    clearFilters,
    filterCount,
    LAST_SEARCH_KEY,
    SCROLL_KEY,
    startMode,
    toQueryString,
    toSearchBody,
    type DiscoverState,
    type Mode,
} from "@/lib/discover";
import type { DiscoverOptions, SearchResults } from "@/lib/types";
import FiltersPanel from "./FiltersPanel";
import ResultCard from "./ResultCard";
import styles from "./DiscoverBoard.module.css";

type DiscoverBoardProps = {
    initialState: DiscoverState;
    initialResults: SearchResults;     // rendered by the server, so the page arrives filled in
    options: DiscoverOptions;
    profileDisciplines: string[];      // "Matched to you" starts from these
};

const MODES: { mode: Mode; label: string }[] = [
    { mode: "matched", label: "Matched to you" },
    { mode: "all", label: "All calls" },
];

const SEARCH_DELAY_MS = 250;     // wait for a pause in typing before searching
const SKELETON_DELAY_MS = 300;   // a fast answer replaces the results without a flash of placeholders

// The same search, in words: the request depends on everything but the panel being open
const searchKey = (state: DiscoverState) => JSON.stringify(toSearchBody(state));

// Discover (design: DISCOVER.md). Every change is written to the page address (lib/discover.ts),
// then searched; "Back to results" from a call returns to the same address and scroll position.
const DiscoverBoard = ({ initialState, initialResults, options, profileDisciplines }: DiscoverBoardProps) => {
    const [state, setState] = useState(initialState);
    const [results, setResults] = useState(initialResults);
    const [searching, setSearching] = useState(false);
    const [showSkeletons, setShowSkeletons] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const lastSearched = useRef(searchKey(initialState));

    const update = (next: DiscoverState) => {
        setState(next);
        // replaceState, not a navigation: the address follows the search without reloading the page
        window.history.replaceState(null, "", `?${toQueryString(next)}`);
    };

    // remember this search for the opportunity page's "Back to results"
    const query = toQueryString(state);
    useEffect(() => {
        try {
            sessionStorage.setItem(LAST_SEARCH_KEY, `?${query}`);
        } catch {
            // storage blocked: "Back to results" opens a fresh Discover instead
        }
    }, [query]);

    // Search whenever the request changes, after a short pause; an older answer never
    // overwrites a newer one (the old request is aborted)
    const key = searchKey(state);
    useEffect(() => {
        if (key === lastSearched.current) {
            return;
        }
        const controller = new AbortController();
        const skeletonTimer = window.setTimeout(() => setShowSkeletons(true), SEARCH_DELAY_MS + SKELETON_DELAY_MS);
        const searchTimer = window.setTimeout(async () => {
            setSearching(true);
            const response = await requestJson<SearchResults>("POST", "/api/discover/search", JSON.parse(key), {
                signal: controller.signal,
            });
            if (controller.signal.aborted) {
                return;
            }
            lastSearched.current = key;
            if (response.ok) {
                setResults(response.data);
                setError(null);
            } else {
                setError(response.error);
            }
            setSearching(false);
            setShowSkeletons(false);
            window.clearTimeout(skeletonTimer);
        }, SEARCH_DELAY_MS);
        return () => {
            controller.abort();
            window.clearTimeout(searchTimer);
            window.clearTimeout(skeletonTimer);
        };
    }, [key]);

    // Back from a call: return to where the artist was in the list
    useEffect(() => {
        try {
            const saved = JSON.parse(sessionStorage.getItem(SCROLL_KEY) ?? "null") as { search: string; y: number } | null;
            if (saved && saved.search === window.location.search) {
                window.scrollTo(0, saved.y);
            }
            sessionStorage.removeItem(SCROLL_KEY);
        } catch {
            // storage blocked: the page simply opens at the top
        }
    }, []);

    const rememberScroll = () => {
        try {
            sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ search: window.location.search, y: window.scrollY }));
        } catch {
            // storage blocked: nothing to remember
        }
    };

    const narrowed = filterCount(state) > 0;
    const clearAll = () => update(clearFilters(state));
    const clearSearchAndFilters = () => update({ ...clearFilters(state), text: "" });

    const eligibleOrCheck = results.results.filter((r) => r.status !== "LIKELY_NOT_ELIGIBLE");
    const notEligible = results.results.filter((r) => r.status === "LIKELY_NOT_ELIGIBLE");
    const order = results.order === "match" ? "best match first" : "nearest deadline first";
    const shown = results.results.length;
    const countLine = searching
        ? "Searching…"
        : shown < results.total
          ? `Top ${shown} of ${results.total} calls · ${order}`
          : `${results.total} ${results.total === 1 ? "call" : "calls"} · ${order}`;

    // how the list is ordered, always shown under the results heading (eligible calls come first in
    // every mode, src/matching/matcher.py); without documents it also says how to get a ranking
    const note =
        state.mode === "all" ? (
            "Every call in OpenArt: eligible calls first, then nearest deadline. Filters still apply."
        ) : results.ranked_by.length > 0 ? (
            "Eligible calls first, then ranked by how well each fits your profile. Filters start from your profile too."
        ) : (
            <>
                <Link href="/documents" className={styles.noteLink}>
                    Upload your statement, CV or portfolio
                </Link>{" "}
                to rank calls by your practice. Until then: eligible calls first, then nearest deadline.
            </>
        );

    const cards = (list: SearchResults["results"]) => (
        <ol className={styles.grid}>
            {list.map((result) => (
                <ResultCard
                    key={result.id}
                    result={result}
                    highlightDeadline={state.mode === "all"}
                    onOpen={rememberScroll}
                />
            ))}
        </ol>
    );

    return (
        <main id="main" className={styles.main}>
            <div className={styles.titleRow}>
                <h1 className={styles.title}>
                    Discover calls<span className={styles.stop}>.</span>
                </h1>
                <div role="group" aria-label="Show" className={styles.modes}>
                    {MODES.map(({ mode, label }) => (
                        <button
                            key={mode}
                            type="button"
                            aria-pressed={state.mode === mode}
                            className={styles.mode}
                            onClick={() => state.mode !== mode && update(startMode(mode, state, profileDisciplines))}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            <div className={styles.searchRow}>
                <div role="search" className={styles.search}>
                    <label htmlFor="call-search" className={styles.visuallyHidden}>
                        Search calls
                    </label>
                    <svg aria-hidden="true" className={styles.searchIcon} width="18" height="18" viewBox="0 0 24 24">
                        <circle cx="10.5" cy="10.5" r="6.5" />
                        <path d="M15.5 15.5L21 21" />
                    </svg>
                    <input
                        id="call-search"
                        type="search"
                        className={styles.searchInput}
                        placeholder="Search by title, organisation or place"
                        maxLength={200}
                        value={state.text}
                        onChange={(event) => update({ ...state, text: event.target.value })}
                    />
                </div>
                <button
                    type="button"
                    className={styles.panelButton}
                    aria-expanded={state.panelOpen}
                    aria-controls="search-options"
                    aria-label={state.panelOpen ? "Hide filters" : "Show filters"}
                    title={state.panelOpen ? "Hide filters" : "Show filters"}
                    onClick={() => update({ ...state, panelOpen: !state.panelOpen })}
                >
                    <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24">
                        <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
                        <circle cx="16" cy="7" r="2.2" />
                        <circle cx="8" cy="17" r="2.2" />
                    </svg>
                    {narrowed && <span aria-hidden="true" className={styles.dot} />}
                </button>
            </div>

            {state.panelOpen && (
                <FiltersPanel state={state} options={options} onChange={update} onClear={clearAll} />
            )}

            <section aria-labelledby="results-heading" className={styles.results}>
                <div className={styles.resultsHead}>
                    <h2 id="results-heading" className={styles.resultsTitle}>
                        Results
                    </h2>
                    <p aria-live="polite" className={styles.count}>
                        {countLine}
                    </p>
                </div>
                <p className={styles.orderNote}>{note}</p>

                {!results.profile_filled && (
                    <p className={styles.banner}>
                        <Link href="/profile" className={styles.bannerLink}>
                            Verdicts use your saved profile. Fill it in for clearer answers →
                        </Link>
                    </p>
                )}

                {error && (
                    <p role="alert" className={styles.error}>
                        {error}
                    </p>
                )}

                {showSkeletons ? (
                    <div className={styles.grid} aria-hidden="true">
                        {[0, 1, 2].map((i) => (
                            <div key={i} className={styles.skeleton} />
                        ))}
                    </div>
                ) : shown === 0 ? (
                    <div className={styles.empty}>
                        <p className={styles.emptyTitle}>No calls match these filters</p>
                        <button type="button" className={styles.emptyButton} onClick={clearSearchAndFilters}>
                            {state.text ? "Clear search and filters" : "Clear filters"}
                        </button>
                    </div>
                ) : (
                    <>
                        {cards(eligibleOrCheck)}
                        {notEligible.length > 0 && (
                            <>
                                <h3 className={styles.subheading}>Likely not eligible · {notEligible.length}</h3>
                                {cards(notEligible)}
                            </>
                        )}
                    </>
                )}
            </section>
        </main>
    );
};

export default DiscoverBoard;
