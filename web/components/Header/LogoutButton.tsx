"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Button from "@/components/Button/Button";
import { sendJson } from "@/lib/api";

const LogoutButton = () => {
    const router = useRouter();
    const [pending, setPending] = useState(false);

    const logOut = async () => {
        setPending(true);
        await sendJson("POST", "/api/auth/logout");
        router.push("/");
        router.refresh(); // re-render the header without the user
    };

    return (
        <Button variant="secondary" onClick={logOut} disabled={pending}>
            {pending ? "Logging out…" : "Log out"}
        </Button>
    );
};

export default LogoutButton;
