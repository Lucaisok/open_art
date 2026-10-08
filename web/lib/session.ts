import "server-only";
import { cache } from "react";
import { cookies } from "next/headers";
import { API_URL } from "./config";
import type { User } from "./types";

const SESSION_COOKIE = "openart_session"; // same name as api/security.py

// The logged-in user, or null. Runs on the server: it forwards the browser's session
// cookie to the API. cache() makes the header and the page share one API call per request.
export const getCurrentUser = cache(async (): Promise<User | null> => {
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!token) {
        return null;
    }
    try {
        const response = await fetch(`${API_URL}/api/auth/me`, {
            headers: { cookie: `${SESSION_COOKIE}=${token}` },
            cache: "no-store",
        });
        return response.ok ? ((await response.json()) as User) : null;
    } catch {
        return null; // API unreachable: treat as logged out rather than crash the page
    }
});
