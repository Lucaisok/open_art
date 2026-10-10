import type { Metadata } from "next";
import Header from "@/components/Header/Header";
import NotFound from "@/components/NotFound/NotFound";

export const metadata: Metadata = { title: "Not found · OpenArt" };

// Any address the app doesn't have. Outside the (site) layout, so it brings the header itself.
export default function NotFoundPage() {
    return (
        <>
            <Header />
            <NotFound />
        </>
    );
}
