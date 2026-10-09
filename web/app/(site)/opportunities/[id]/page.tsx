import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { cache } from "react";
import OpportunityView from "@/components/Opportunity/OpportunityView";
import { apiGetOrNull } from "@/lib/server-api";
import { getCurrentUser } from "@/lib/session";
import type { Opportunity } from "@/lib/types";

type OpportunityPageProps = { params: Promise<{ id: string }> };

// cache(): the title and the page share one API call per request
const load = cache((id: string) => apiGetOrNull<Opportunity>(`/api/opportunities/${encodeURIComponent(id)}`));

export async function generateMetadata({ params }: OpportunityPageProps): Promise<Metadata> {
    const call = (await getCurrentUser()) ? await load((await params).id) : null;
    return { title: call ? `${call.title} · OpenArt` : "Call · OpenArt" };
}

// One call: its facts, and "Can you apply?" with every eligibility sentence quoted
export default async function OpportunityPage({ params }: OpportunityPageProps) {
    if (!(await getCurrentUser())) {
        redirect("/"); // private page: logged-out visitors go to the login form
    }
    const call = await load((await params).id);
    if (!call) {
        notFound();
    }
    return <OpportunityView call={call} />;
}
