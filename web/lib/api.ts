// Calls to the API from the browser. They go to /api/... on this same site, which
// Next forwards to FastAPI (next.config.ts), so the session cookie travels with them.

export type ApiResult = { ok: true } | { ok: false; error: string };

// A request whose answer we need: the data, or one error sentence plus, for invalid form
// values (422), the message for each field ("birth_date" -> "Birth date can't be in the future.")
export type ApiData<T> =
    | { ok: true; data: T }
    | { ok: false; status: number; error: string; fieldErrors: Record<string, string> };

type ValidationError = { loc: (string | number)[]; type: string; msg: string };

const OFFLINE = "Can't reach the server. Check your connection and try again.";
const GENERIC = "Something went wrong. Please try again.";

// pydantic prefixes the messages we raise ourselves with "Value error, "
const cleanMessage = (msg: string) => msg.replace(/^Value error, /, "");

// Turns FastAPI's error body into one sentence for the person filling in the form
const errorFromBody = (status: number, body: unknown): string => {
    if (status === 413) {
        // also sent by nginx before the request reaches the API, as HTML, so checked first
        return "The file is larger than 10 MB.";
    }
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") {
        return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as ValidationError;
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
        if (first.type === "value_error") {
            return cleanMessage(first.msg);
        }
    }
    return GENERIC;
};

// The per-field messages of a 422, keyed by the field name (the last part of `loc`)
const fieldErrorsFromBody = (body: unknown): Record<string, string> => {
    const detail = (body as { detail?: unknown } | null)?.detail;
    const errors: Record<string, string> = {};
    if (Array.isArray(detail)) {
        for (const item of detail as ValidationError[]) {
            const field = String(item.loc[item.loc.length - 1]);
            errors[field] ??= item.type === "value_error" ? cleanMessage(item.msg) : "Check this value.";
        }
    }
    return errors;
};

const parseJson = (text: string): unknown => {
    try {
        return JSON.parse(text);
    } catch {
        return null; // not JSON (an nginx error page, for example)
    }
};

// Sends one request and reduces the answer to ok / an error sentence
const send = async (path: string, init: RequestInit): Promise<ApiResult> => {
    try {
        const response = await fetch(path, init);
        if (response.ok) {
            return { ok: true };
        }
        return { ok: false, error: errorFromBody(response.status, parseJson(await response.text())) };
    } catch {
        return { ok: false, error: OFFLINE };
    }
};

export const sendJson = (method: "POST" | "DELETE", path: string, body?: unknown): Promise<ApiResult> =>
    send(path, {
        method,
        headers: body === undefined ? undefined : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
    });

// Like sendJson, but returns the answer's data. `signal` cancels it (a newer search replaces it).
export const requestJson = async <T>(
    method: "GET" | "POST" | "PUT" | "DELETE",
    path: string,
    body?: unknown,
    { signal }: { signal?: AbortSignal } = {},
): Promise<ApiData<T>> => {
    try {
        const response = await fetch(path, {
            method,
            signal,
            headers: body === undefined ? undefined : { "Content-Type": "application/json" },
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        const parsed = parseJson(await response.text());
        if (response.ok) {
            return { ok: true, data: parsed as T };
        }
        return {
            ok: false,
            status: response.status,
            error: errorFromBody(response.status, parsed),
            fieldErrors: response.status === 422 ? fieldErrorsFromBody(parsed) : {},
        };
    } catch {
        return { ok: false, status: 0, error: OFFLINE, fieldErrors: {} };
    }
};

// Uploads one file as multipart form data, in the field "file" (FastAPI's UploadFile), and
// reports how much was sent. XMLHttpRequest, not fetch: fetch can't report upload progress.
// `abort()` cancels it; the promise then resolves with { ok: false, error: "aborted" }.
export const uploadFile = <T>(
    method: "PUT" | "POST",
    path: string,
    file: File,
    onProgress: (fraction: number) => void,
): { done: Promise<ApiData<T>>; abort: () => void } => {
    const request = new XMLHttpRequest();
    const done = new Promise<ApiData<T>>((resolve) => {
        request.upload.onprogress = (event) => {
            if (event.lengthComputable) {
                onProgress(event.loaded / event.total);
            }
        };
        request.onload = () => {
            const parsed = parseJson(request.responseText);
            if (request.status >= 200 && request.status < 300) {
                resolve({ ok: true, data: parsed as T });
            } else {
                resolve({ ok: false, status: request.status, error: errorFromBody(request.status, parsed), fieldErrors: {} });
            }
        };
        request.onerror = () => resolve({ ok: false, status: 0, error: OFFLINE, fieldErrors: {} });
        request.onabort = () => resolve({ ok: false, status: 0, error: "aborted", fieldErrors: {} });
    });
    const form = new FormData();
    form.append("file", file);
    request.open(method, path);
    request.send(form);
    return { done, abort: () => request.abort() };
};
