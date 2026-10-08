// Where the FastAPI backend listens. The same address locally (docker compose) and
// on the VPS, so it rarely needs overriding; set API_URL to point elsewhere.
export const API_URL = process.env.API_URL ?? "http://127.0.0.1:8040";
