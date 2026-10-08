import "server-only";
import { cookies } from "next/headers";
import { API_URL } from "./config";
import type { DocumentInfo } from "./types";

const SESSION_COOKIE = "openart_session"; // same name as api/security.py and lib/session.ts

// The logged-in artist's documents, read on the server (like getCurrentUser in lib/session.ts)
export const getDocuments = async (): Promise<DocumentInfo[]> => {
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!token) {
        return [];
    }
    const response = await fetch(`${API_URL}/api/documents`, {
        headers: { cookie: `${SESSION_COOKIE}=${token}` },
        cache: "no-store",
    });
    if (!response.ok) {
        throw new Error(`GET /api/documents failed: ${response.status}`);
    }
    return (await response.json()) as DocumentInfo[];
};
