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
export type DiscoverOptions = components["schemas"]["DiscoverOptions"];
export type SearchBody = components["schemas"]["SearchIn"];
export type SearchResults = components["schemas"]["SearchOut"];
export type SearchResult = components["schemas"]["ResultOut"];
export type Opportunity = components["schemas"]["OpportunityOut"];
export type VerdictStatus = SearchResult["status"];
export type ProjectsData = components["schemas"]["ProjectsOut"];
export type ProjectItem = components["schemas"]["ProjectOut"];
export type ProjectInput = components["schemas"]["ProjectIn"];
export type ApplicationData = components["schemas"]["ApplicationOut"];
export type ApplicationItem = components["schemas"]["ItemOut"];
export type AgentMessage = components["schemas"]["MessageOut"];
export type AgentTurn = components["schemas"]["TurnOut"];
export type ProjectSelection = components["schemas"]["Selection"];
export type ProjectChoice = components["schemas"]["ProjectChoiceOut"];
export type ImageInfo = components["schemas"]["ImageOut"];
export type ProjectImages = components["schemas"]["ProjectImagesOut"];
export type SavedCalls = components["schemas"]["SavedCallsOut"];
export type SavedCall = components["schemas"]["SavedCallOut"];
