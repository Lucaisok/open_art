import "server-only";
import { cookies } from "next/headers";
import { API_URL } from "./config";

const SESSION_COOKIE = "openart_session"; // same name as api/security.py and lib/session.ts

// GET from the API on the server, as the logged-in artist (their session cookie is forwarded,
// like getCurrentUser in lib/session.ts). For pages that need the artist's data on first render.
export const apiGet = async <T>(path: string): Promise<T> => {
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    const response = await fetch(`${API_URL}${path}`, {
        headers: token ? { cookie: `${SESSION_COOKIE}=${token}` } : undefined,
        cache: "no-store",
    });
    if (!response.ok) {
        throw new Error(`GET ${path} failed: ${response.status}`);
    }
    return (await response.json()) as T;
};

// POST to the API on the server, as the logged-in artist: for reads that take a body
// (the Discover search, so the page arrives with its results already in it)
export const apiPost = async <T>(path: string, body: unknown): Promise<T> => {
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    const response = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { cookie: `${SESSION_COOKIE}=${token}` } : {}) },
        body: JSON.stringify(body),
        cache: "no-store",
    });
    if (!response.ok) {
        throw new Error(`POST ${path} failed: ${response.status}`);
    }
    return (await response.json()) as T;
};

// Like apiGet, but null when the API answers 404 (the page then shows "not found")
export const apiGetOrNull = async <T>(path: string): Promise<T | null> => {
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    const response = await fetch(`${API_URL}${path}`, {
        headers: token ? { cookie: `${SESSION_COOKIE}=${token}` } : undefined,
        cache: "no-store",
    });
    if (response.status === 404) {
        return null;
    }
    if (!response.ok) {
        throw new Error(`GET ${path} failed: ${response.status}`);
    }
    return (await response.json()) as T;
};
