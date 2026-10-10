// Discover's state lives in the page address (/discover?mode=matched&type=Residency...), so
// "Back to results" from a call returns to the same search, and a search can be reloaded or
// bookmarked. Used by the server page (first render) and by the client board (every change).
import type { SearchBody, VerdictStatus } from "./types";

export type Mode = "matched" | "all";

export type DiscoverState = {
    mode: Mode;
    text: string;          // the search box
    types: string[];
    disciplines: string[];
    country: string;       // "" = any country
    fundedOnly: boolean;
    noFee: boolean;
    panelOpen: boolean;    // the filters panel
};

// What Next gives a server page as `searchParams`: a repeated key arrives as an array
type ParamRecord = Record<string, string | string[] | undefined>;

const list = (value: string | string[] | undefined): string[] =>
    value === undefined ? [] : Array.isArray(value) ? value : [value];

const one = (value: string | string[] | undefined): string => list(value)[0] ?? "";

export const parseState = (params: ParamRecord): DiscoverState => ({
    mode: one(params.mode) === "all" ? "all" : "matched",
    text: one(params.q),
    types: list(params.type),
    disciplines: list(params.discipline),
    country: one(params.country),
    fundedOnly: one(params.funded) === "1",
    noFee: one(params.nofee) === "1",
    panelOpen: one(params.panel) === "1",
});

export const toQueryString = (state: DiscoverState): string => {
    const params = new URLSearchParams({ mode: state.mode });
    if (state.text) params.set("q", state.text);
    state.types.forEach((t) => params.append("type", t));
    state.disciplines.forEach((d) => params.append("discipline", d));
    if (state.country) params.set("country", state.country);
    if (state.fundedOnly) params.set("funded", "1");
    if (state.noFee) params.set("nofee", "1");
    if (state.panelOpen) params.set("panel", "1");
    return params.toString();
};

// A mode's starting filters (product owner, workflow.MD step 5): "Matched to you" starts from
// the saved profile's disciplines, "All calls" from none. The search text and the panel stay.
export const startMode = (mode: Mode, current: DiscoverState, profileDisciplines: string[]): DiscoverState => ({
    ...current,
    mode,
    types: [],
    disciplines: mode === "matched" ? profileDisciplines : [],
    country: "",
    fundedOnly: false,
    noFee: false,
});

export const clearFilters = (state: DiscoverState): DiscoverState => ({
    ...state,
    types: [],
    disciplines: [],
    country: "",
    fundedOnly: false,
    noFee: false,
});

export const filterCount = (state: DiscoverState): number =>
    state.types.length + state.disciplines.length + (state.country ? 1 : 0) + (state.fundedOnly ? 1 : 0) + (state.noFee ? 1 : 0);

// Calls per page (api/discover.py PAGE_SIZE): the board loads the next page as the artist scrolls
export const PAGE_SIZE = 30;

export const toSearchBody = (state: DiscoverState): SearchBody => ({
    mode: state.mode,
    text: state.text.trim(),
    types: state.types,
    disciplines: state.disciplines,
    country: state.country || null,
    funded_only: state.fundedOnly,
    no_fee: state.noFee,
    offset: 0,
    limit: PAGE_SIZE,
});

// -- how a call is shown -------------------------------------------------------------------------

// Whole days from today to an ISO date ("2027-03-14"), counted on calendar dates in UTC so the
// server's first render and the browser agree
export const daysUntil = (iso: string): number => {
    const now = new Date();
    const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const [y, m, d] = iso.split("-").map(Number);
    return Math.round((Date.UTC(y, m - 1, d) - today) / 86_400_000);
};

export const deadlineLabel = (deadline: string | null | undefined): string => {
    if (!deadline) return "No deadline stated";
    const days = daysUntil(deadline);
    if (days <= 0) return "Deadline today"; // closed calls are never listed
    if (days === 1) return "Deadline tomorrow";
    return `Deadline in ${days} days`;
};

// The opportunity page's deadline: "14 Mar 2027 · in 45 days"
export const deadlineFact = (deadline: string | null | undefined): string => {
    if (!deadline) return "No deadline stated";
    const [y, m, d] = deadline.split("-").map(Number);
    const date = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
        day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
    });
    const days = daysUntil(deadline);
    if (days < 0) return `Closed on ${date}`;
    if (days === 0) return `${date} · today`;
    if (days === 1) return `${date} · tomorrow`;
    return `${date} · in ${days} days`;
};

// The last Discover address, kept per browser tab so the opportunity page's "Back to results"
// returns to that search (DiscoverBoard writes it, BackToResults reads it)
export const LAST_SEARCH_KEY = "discover-last-search";

// The scroll position to return to: { search, y }, written when a result is opened,
// read and removed by DiscoverBoard when it opens on that same search
export const SCROLL_KEY = "discover-scroll";

export const placeLabel = (city: string | null | undefined, countries: string[]): string =>
    [city, countries.join(" · ")].filter(Boolean).join(", ") || "Place not stated";

// Never colour alone: every verdict has its own icon and words too
export const VERDICTS: Record<VerdictStatus, { icon: string; label: string }> = {
    ELIGIBLE: { icon: "✓", label: "Eligible" },
    CHECK: { icon: "○", label: "Check" },
    LIKELY_NOT_ELIGIBLE: { icon: "✕", label: "Likely not eligible" },
};
