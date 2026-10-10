import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import DiscoverBoard from "@/components/Discover/DiscoverBoard";
import {
    LAST_SEARCH_COOKIE,
    paramsFromQuery,
    parseState,
    startMode,
    toQueryString,
    toSearchBody,
    type DiscoverState,
} from "@/lib/discover";
import { apiGet, apiPost } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { DiscoverOptions, ProfileData, SearchResults } from "@/lib/types";

export const metadata: Metadata = { title: "Discover calls · OpenArt" };

type DiscoverPageProps = { searchParams: Promise<Record<string, string | string[] | undefined>> };

// Discover: the calls, ranked by the artist's documents or by deadline, each with its verdict.
// The search lives in the address; the server runs it once so the page arrives with its results.
// A bare /discover is not redirected (a redirect showed the page, blanked it, then showed it again):
// the server picks the search itself and the board writes its address into the bar afterwards.
export default async function DiscoverPage({ searchParams }: DiscoverPageProps) {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const params = await searchParams;
    const profile = await apiGet<ProfileData>("/api/profile");
    const profileDisciplines = profile.values.disciplines ?? [];

    // a fresh visit: "Matched to you", with the filters pre-set from the saved profile
    const fresh = startMode("matched", parseState({}), profileDisciplines);
    let state: DiscoverState;
    let remembered = false;
    if (Object.keys(params).length > 0) {
        state = parseState(params);
    } else {
        // a bare /discover: the artist's last search in this browser session, if there is one
        const last = (await cookies()).get(LAST_SEARCH_COOKIE)?.value;
        remembered = Boolean(last);
        state = last ? parseState(paramsFromQuery(decodeURIComponent(last))) : fresh;
    }

    const optionsRequest = apiGet<DiscoverOptions>("/api/discover/options");
    let results: SearchResults;
    try {
        results = await apiPost<SearchResults>("/api/discover/search", toSearchBody(state));
    } catch (error) {
        if (!remembered) {
            throw error;
        }
        // a remembered search the API refuses (a filter value that no longer exists): start afresh
        state = fresh;
        results = await apiPost<SearchResults>("/api/discover/search", toSearchBody(state));
    }
    const options = await optionsRequest;

    // key: a new address (e.g. the header's Discover link) starts the board afresh
    return (
        <DiscoverBoard
            key={toQueryString(state)}
            initialState={state}
            initialResults={results}
            options={options}
            profileDisciplines={profileDisciplines}
        />
    );
}
