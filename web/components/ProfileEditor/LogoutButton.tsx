"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { sendJson } from "@/lib/api";
import { forgetSearch } from "@/lib/discover";

// On the profile page's Account box (the header has no Log out)
const LogoutButton = ({ className }: { className?: string }) => {
    const router = useRouter();
    const [pending, setPending] = useState(false);

    const logOut = async () => {
        setPending(true);
        await sendJson("POST", "/api/auth/logout");
        forgetSearch(); // the next artist on this browser starts from their own profile
        router.push("/"); // the login form
        router.refresh(); // re-render the header without the user
    };

    return (
        <button type="button" className={className} onClick={logOut} disabled={pending}>
            {pending ? "Logging out…" : "Log out"}
        </button>
    );
};

export default LogoutButton;
