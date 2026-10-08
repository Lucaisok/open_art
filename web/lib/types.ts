// Shortcuts to the types generated from the API (lib/api-types.ts, `npm run types:api`).
// Never edit api-types.ts by hand: regenerate it when the API changes.
import type { components } from "./api-types";

export type User = components["schemas"]["UserOut"];
export type DocumentInfo = components["schemas"]["DocumentOut"];
export type DocumentKind = DocumentInfo["kind"];
export type ProfileValues = components["schemas"]["ProfileValues"];
export type ProfileData = components["schemas"]["ProfileOut"];
export type Evidence = components["schemas"]["Evidence"];
export type Suggestion = components["schemas"]["Suggestion"];
export type ProfileOptions = components["schemas"]["Options"];
