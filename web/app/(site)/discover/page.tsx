import type { Metadata } from "next";
import { redirect } from "next/navigation";
import DiscoverBoard from "@/components/Discover/DiscoverBoard";
import { parseState, startMode, toQueryString, toSearchBody } from "@/lib/discover";
import { apiGet, apiPost } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { DiscoverOptions, ProfileData, SearchResults } from "@/lib/types";

export const metadata: Metadata = { title: "Discover calls · OpenArt" };

type DiscoverPageProps = { searchParams: Promise<Record<string, string | string[] | undefined>> };

// Discover: the calls, ranked by the artist's documents or by deadline, each with its verdict.
// The search lives in the address; the server runs it once so the page arrives with its results.
export default async function DiscoverPage({ searchParams }: DiscoverPageProps) {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const params = await searchParams;
    const profile = await apiGet<ProfileData>("/api/profile");
    const profileDisciplines = profile.values.disciplines ?? [];

    // a fresh visit: "Matched to you", with the filters pre-set from the saved profile
    if (Object.keys(params).length === 0) {
        redirect(`/discover?${toQueryString(startMode("matched", parseState({}), profileDisciplines))}`);
    }

    const state = parseState(params);
    const [options, results] = await Promise.all([
        apiGet<DiscoverOptions>("/api/discover/options"),
        apiPost<SearchResults>("/api/discover/search", toSearchBody(state)),
    ]);

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
