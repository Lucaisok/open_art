import NotFound from "@/components/NotFound/NotFound";

// A call that isn't in OpenArt (a mistyped address, or a call removed from the corpus)
export default function CallNotFound() {
    return (
        <NotFound
            title="Call not found"
            message="This call isn't in OpenArt any more, or the address is wrong. There are plenty of others."
        />
    );
}
