// What the profile page knows about each field: its label, and how to show a value in words.
// The field names are the API's (ProfileValues in api/profile.py).
import type { Evidence, ProfileOptions, ProfileValues } from "@/lib/types";

export type FieldName = keyof ProfileValues;
export type EvidenceMap = Record<string, Evidence>;

export const FIELD_LABELS: Record<FieldName, string> = {
    birth_date: "Birth date",
    nationalities: "Nationalities",
    residence_country: "Country of residence",
    applicant_type: "Applying as",
    disciplines: "Disciplines",
    career_stage: "Career stage",
    active_since: "Active since",
    currently_enrolled: "Currently a student",
    graduation_year: "Graduation year",
    has_degree: "Degree",
    degree_field: "Field of most recent degree",
};

export const APPLICANT_TYPES = [
    { value: "individual", label: "Individual" },
    { value: "group", label: "Group or collective" },
    { value: "organisation", label: "Organisation" },
] as const;

// the API's career stage values, in the words shown to the artist
export const CAREER_STAGE_LABELS: Record<string, string> = {
    Student: "Student",
    "Emerging/Early-Career": "Emerging / early-career",
    "Mid-Career": "Mid-career",
    "Established/Professional": "Established",
};

export const formatDate = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "long",
        year: "numeric",
        timeZone: "UTC",
    });

// A value as words, e.g. ["HU", "AT"] -> "Hungary, Austria". Empty -> null.
export const formatValue = (field: FieldName, value: unknown, options: ProfileOptions): string | null => {
    if (value === null || value === undefined || (Array.isArray(value) && value.length === 0) || value === "") {
        return null;
    }
    const countryName = (code: string) => options.countries.find((c) => c.code === code)?.name ?? code;
    switch (field) {
        case "birth_date":
            return formatDate(String(value));
        case "nationalities":
            return (value as string[]).map(countryName).join(", ");
        case "residence_country":
            return countryName(String(value));
        case "disciplines":
            return (value as string[]).join(", ");
        case "applicant_type":
            return APPLICANT_TYPES.find((t) => t.value === value)?.label ?? String(value);
        case "career_stage":
            return CAREER_STAGE_LABELS[String(value)] ?? String(value);
        case "currently_enrolled":
        case "has_degree":
            return value ? "Yes" : "No";
        default:
            return String(value);
    }
};
