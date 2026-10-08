// Calls to the API from the browser. They go to /api/... on this same site, which
// Next forwards to FastAPI (next.config.ts), so the session cookie travels with them.

export type ApiResult = { ok: true } | { ok: false; error: string };

type ValidationError = { loc: (string | number)[]; type: string };

// Turns FastAPI's error responses into one sentence for the person filling in the form
const errorMessage = async (response: Response): Promise<string> => {
    if (response.status === 413) {
        // also sent by nginx before the request reaches the API, as HTML, so checked first
        return "The file is larger than 10 MB.";
    }
    try {
        const body = await response.json();
        if (typeof body.detail === "string") {
            return body.detail;
        }
        if (Array.isArray(body.detail) && body.detail.length > 0) {
            const first = body.detail[0] as ValidationError;
            const field = String(first.loc[first.loc.length - 1]);
            if (field === "email") {
                return "Enter a valid email address.";
            }
            if (field.includes("password") && first.type === "string_too_short") {
                return "The password must be at least 10 characters long.";
            }
            if (field.includes("password") && first.type === "string_too_long") {
                return "The password must be at most 200 characters long.";
            }
        }
    } catch {
        // not JSON: fall through to the generic message
    }
    return "Something went wrong. Please try again.";
};

// Sends one request and reduces the answer to ok / an error sentence
const send = async (path: string, init: RequestInit): Promise<ApiResult> => {
    try {
        const response = await fetch(path, init);
        return response.ok ? { ok: true } : { ok: false, error: await errorMessage(response) };
    } catch {
        return { ok: false, error: "Can't reach the server. Check your connection and try again." };
    }
};

export const sendJson = (method: "POST" | "DELETE", path: string, body?: unknown): Promise<ApiResult> =>
    send(path, {
        method,
        headers: body === undefined ? undefined : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
    });

// Uploads one file as multipart form data, in the field "file" (FastAPI's UploadFile).
// No Content-Type header: the browser sets it, with the multipart boundary.
export const sendFile = (path: string, file: File): Promise<ApiResult> => {
    const form = new FormData();
    form.append("file", file);
    return send(path, { method: "PUT", body: form });
};
