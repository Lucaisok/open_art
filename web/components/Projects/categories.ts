import type { ProjectInput } from "@/lib/types";

export type Category = NonNullable<ProjectInput["category"]>;

// What a project is (api/projects.py, Category). The singular labels a card, the plural heads a group.
export const CATEGORIES: { value: Category; label: string; plural: string }[] = [
    { value: "work", label: "Work", plural: "Works" },
    { value: "exhibition", label: "Exhibition", plural: "Exhibitions and screenings" },
    { value: "performance", label: "Performance", plural: "Performances" },
    { value: "commission", label: "Commission", plural: "Commissions" },
];

export const categoryLabel = (category: ProjectInput["category"] | string) =>
    CATEGORIES.find((c) => c.value === category)?.label ?? null;
