"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { sendJson } from "@/lib/api";

const LogoutButton = ({ className }: { className?: string }) => {
    const router = useRouter();
    const [pending, setPending] = useState(false);

    const logOut = async () => {
        setPending(true);
        await sendJson("POST", "/api/auth/logout");
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
