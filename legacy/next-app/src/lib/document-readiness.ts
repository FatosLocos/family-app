import { dateKey, dateSortValue } from "@/lib/date-keys";
import type { AppData, HouseholdDocument } from "@/lib/types";

const essentialCategories = ["Identiteit", "Verzekering", "Contract", "Garantie", "Medisch"];
const dateCriticalCategories = ["identiteit", "verzekering", "contract", "garantie"];

export type DocumentReadinessAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type DocumentReadiness = {
  total: number;
  completeDocuments: number;
  missingLocation: HouseholdDocument[];
  importantWithoutExpiry: HouseholdDocument[];
  missingEssentials: string[];
  expiringQuarter: HouseholdDocument[];
  sensitive: HouseholdDocument[];
  score: number;
  totalChecks: number;
  percent: number;
  actions: DocumentReadinessAction[];
  nextAction: DocumentReadinessAction;
};

export function buildDocumentReadiness(data: Pick<AppData, "householdDocuments">, today: string): DocumentReadiness {
  const todayKey = dateKey(today) ?? today;
  const nextQuarter = addDays(todayKey, 90);
  const categoriesPresent = new Set(data.householdDocuments.map((document) => document.category.toLowerCase()));
  const missingEssentials = essentialCategories.filter((category) => !categoriesPresent.has(category.toLowerCase()));
  const missingLocation = data.householdDocuments.filter((document) => !document.location);
  const importantWithoutExpiry = data.householdDocuments.filter((document) =>
    dateCriticalCategories.includes(document.category.toLowerCase()) && !document.expires_at,
  );
  const expiringQuarter = data.householdDocuments
    .filter((document) => {
      const expiresAt = dateKey(document.expires_at);
      return expiresAt && expiresAt >= todayKey && expiresAt <= nextQuarter;
    })
    .sort((a, b) => dateSortValue(a.expires_at) - dateSortValue(b.expires_at));
  const sensitive = data.householdDocuments.filter((document) => document.is_sensitive);
  const completeDocuments = data.householdDocuments.filter((document) =>
    document.location && (document.expires_at || !dateCriticalCategories.includes(document.category.toLowerCase())),
  ).length;
  const actions: DocumentReadinessAction[] = [
    {
      id: "documents",
      title: "Documenten toegevoegd",
      detail: data.householdDocuments.length > 0 ? `${data.householdDocuments.length} document${data.householdDocuments.length === 1 ? "" : "en"} opgeslagen.` : "Voeg je eerste document toe.",
      href: "/documenten",
      done: data.householdDocuments.length > 0,
    },
    {
      id: "locations",
      title: "Bewaarplekken compleet",
      detail: missingLocation.length === 0 ? "Alle documenten hebben een fysieke of digitale locatie." : `${missingLocation.length} document${missingLocation.length === 1 ? "" : "en"} mist een bewaarplek.`,
      href: "/documenten",
      done: missingLocation.length === 0,
    },
    {
      id: "expiry",
      title: "Vervaldata voor belangrijke stukken",
      detail: importantWithoutExpiry.length === 0 ? "Belangrijke documenten hebben een relevante datum." : `${importantWithoutExpiry.length} belangrijk document${importantWithoutExpiry.length === 1 ? "" : "en"} mist een vervaldatum.`,
      href: "/documenten",
      done: importantWithoutExpiry.length === 0,
    },
    {
      id: "essentials",
      title: "Essentiele categorieen aanwezig",
      detail: missingEssentials.length <= 1 ? "De belangrijkste documentcategorieen zijn bijna compleet." : `${missingEssentials.slice(0, 3).join(", ")} ontbreken nog.`,
      href: "/documenten",
      done: missingEssentials.length <= 1,
    },
    {
      id: "sensitive",
      title: "Gevoelige stukken gelabeld",
      detail: sensitive.length > 0 ? `${sensitive.length} document${sensitive.length === 1 ? "" : "en"} als gevoelig gemarkeerd.` : "Markeer privacygevoelige referenties of documenten.",
      href: "/documenten",
      done: sensitive.length > 0,
    },
  ];
  const score = actions.filter((action) => action.done).length;

  return {
    total: data.householdDocuments.length,
    completeDocuments,
    missingLocation,
    importantWithoutExpiry,
    missingEssentials,
    expiringQuarter,
    sensitive,
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
    nextAction: actions.find((action) => !action.done) ?? {
      id: "backup",
      title: "Documentkluis is goed ingericht",
      detail: "Gebruik Data & backup om je gezinsdata te exporteren.",
      href: "/data",
      done: true,
    },
  };
}

function addDays(date: string, days: number) {
  const value = new Date(`${date}T12:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}
