// Shortcuts to the types generated from the API (lib/api-types.ts, `npm run types:api`).
// Never edit api-types.ts by hand: regenerate it when the API changes.
import type { components } from "./api-types";

export type User = components["schemas"]["UserOut"];
export type DocumentInfo = components["schemas"]["DocumentOut"];
export type DocumentKind = DocumentInfo["kind"];
