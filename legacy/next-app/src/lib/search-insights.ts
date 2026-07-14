import { buildSearchResults, type SearchResult } from "@/lib/search";
import type { AppData } from "@/lib/types";

export type SearchModuleCount = {
  module: string;
  count: number;
};

export type SearchAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type SearchInsight = {
  query: string;
  trimmedQuery: string;
  results: SearchResult[];
  filteredResults: SearchResult[];
  groupedResults: Record<string, SearchResult[]>;
  moduleCounts: SearchModuleCount[];
  activeModule: string;
  suggestedQueries: string[];
  bestResult: SearchResult | null;
  dominantModule: SearchModuleCount | null;
  exactTitleMatches: number;
  maskedResults: number;
  searchState: string;
  score: number;
  totalChecks: number;
  percent: number;
  actions: SearchAction[];
};

export function buildSearchInsight(data: AppData, query: string, moduleFilter = "alles"): SearchInsight {
  const results = buildSearchResults(data, query);
  const moduleCounts = countByModule(results);
  const moduleCountMap = new Map(moduleCounts.map((item) => [item.module, item.count]));
  const activeModule = moduleFilter === "alles" || !moduleCountMap.has(moduleFilter) ? "alles" : moduleFilter;
  const filteredResults = activeModule === "alles" ? results : results.filter((result) => result.module === activeModule);
  const groupedResults = filteredResults.reduce<Record<string, SearchResult[]>>((groups, result) => {
    groups[result.module] = [...(groups[result.module] ?? []), result];
    return groups;
  }, {});
  const suggestedQueries = buildSuggestedQueries(data);
  const trimmedQuery = query.trim();
  const bestResult = filteredResults[0] ?? results[0] ?? null;
  const dominantModule = moduleCounts[0] ?? null;
  const exactTitleMatches = results.filter((result) => result.title.toLowerCase() === trimmedQuery.toLowerCase()).length;
  const maskedResults = filteredResults.filter((result) => result.privacy === "masked").length;
  const searchState = trimmedQuery.length < 2
    ? "Typ minimaal twee tekens om te zoeken."
    : results.length === 0
      ? "Geen resultaten gevonden. Probeer een bredere term of een module."
      : `${results.length} resultaat${results.length === 1 ? "" : "en"} in ${moduleCounts.length} module${moduleCounts.length === 1 ? "" : "s"}.`;

  const actions: SearchAction[] = [
    {
      id: "query",
      title: "Zoekterm bruikbaar",
      detail: trimmedQuery.length >= 2 ? `"${trimmedQuery}" wordt gezocht` : "Typ minimaal twee tekens.",
      href: "/zoeken",
      done: trimmedQuery.length >= 2,
    },
    {
      id: "results",
      title: "Resultaten gevonden",
      detail: results.length > 0 ? `${results.length} resultaat${results.length === 1 ? "" : "en"}` : "Geen resultaten op deze zoekterm.",
      href: bestResult?.href ?? "/snel",
      done: trimmedQuery.length < 2 || results.length > 0,
    },
    {
      id: "coverage",
      title: "Moduledekking",
      detail: moduleCounts.length > 1 ? `${moduleCounts.length} modules gevonden` : moduleCounts[0] ? `Alleen ${moduleCounts[0].module}` : "Nog geen moduledekking.",
      href: "/inrichting",
      done: trimmedQuery.length < 2 || moduleCounts.length > 1,
    },
    {
      id: "filter",
      title: "Filter hanteerbaar",
      detail: activeModule === "alles" ? "Alle modules zichtbaar" : `Gefilterd op ${activeModule}`,
      href: `/zoeken?q=${encodeURIComponent(query)}`,
      done: activeModule === "alles" || filteredResults.length > 0,
    },
    {
      id: "privacy",
      title: "Gevoelige data afgeschermd",
      detail: maskedResults > 0 ? `${maskedResults} resultaat${maskedResults === 1 ? "" : "en"} met gemaskeerde inhoud.` : "Document- en huisinfo-waarden worden gemaskeerd in resultaten.",
      href: "/data",
      done: true,
    },
  ];
  const score = actions.filter((action) => action.done).length;

  return {
    query,
    trimmedQuery,
    results,
    filteredResults,
    groupedResults,
    moduleCounts,
    activeModule,
    suggestedQueries,
    bestResult,
    dominantModule,
    exactTitleMatches,
    maskedResults,
    searchState,
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
  };
}

function countByModule(results: SearchResult[]) {
  const counts = new Map<string, number>();
  results.forEach((result) => counts.set(result.module, (counts.get(result.module) ?? 0) + 1));
  return Array.from(counts.entries())
    .map(([module, count]) => ({ module, count }))
    .sort((a, b) => b.count - a.count || a.module.localeCompare(b.module));
}

function buildSuggestedQueries(data: AppData) {
  return [
    data.tasks.find((task) => task.status === "open")?.title,
    data.shoppingItems.find((item) => !item.checked)?.name,
    data.financeItems.find((item) => item.status !== "betaald")?.category,
    data.calendarEvents[0]?.location,
    data.householdDocuments[0]?.category,
  ]
    .filter((value): value is string => Boolean(value))
    .filter((value, index, values) => values.indexOf(value) === index)
    .slice(0, 5);
}
