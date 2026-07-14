import Link from "next/link";
import { ArrowRight, Compass, Filter, Search, ShieldCheck } from "lucide-react";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { demoData } from "@/lib/demo-data";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";
import { buildSearchInsight } from "@/lib/search-insights";
import { getAppData, getUser } from "@/lib/local-data";

export const dynamic = "force-dynamic";

export default async function SearchPage({
  searchParams,
}: {
  searchParams?: Promise<{ q?: string | string[]; module?: string | string[] }>;
}) {
  const params = await searchParams;
  const query = Array.isArray(params?.q) ? params?.q[0] ?? "" : params?.q ?? "";
  const moduleFilter = Array.isArray(params?.module) ? params?.module[0] ?? "alles" : params?.module ?? "alles";

  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <SearchContent data={await getLocalAppData()} query={query} moduleFilter={moduleFilter} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <SearchContent data={data} query={query} moduleFilter={moduleFilter} />;
}

function SearchContent({ data, query, moduleFilter, demo = false }: { data: typeof demoData; query: string; moduleFilter: string; demo?: boolean }) {
  const insight = buildSearchInsight(data, query, moduleFilter);

  return (
    <AppShell demo={demo}>
      <section className="dashboard-hero">
        <div className="grid">
          <div>
            <h1>Zoeken</h1>
            <p className="muted">Zoek in taken, boodschappen, documenten, agenda, contacten, onderhoud en meer.</p>
          </div>
          <form className="search-box" action="/zoeken" data-instant-search>
            <Search size={18} />
            <input name="q" defaultValue={query} placeholder="Zoek op paspoort, tandarts, pasta, hypotheek..." autoFocus />
            {insight.activeModule !== "alles" && <input type="hidden" name="module" value={insight.activeModule} />}
            <button className="button primary">Zoeken</button>
          </form>
          <div className="search-suggestions">
            {insight.suggestedQueries.map((suggestion) => (
              <Link href={`/zoeken?q=${encodeURIComponent(suggestion)}`} key={suggestion}>{suggestion}</Link>
            ))}
          </div>
        </div>
        <aside className="today-panel">
          <div>
            <span className="eyebrow">Zoekstatus</span>
            <h2 style={{ margin: "8px 0 0" }}>{insight.trimmedQuery.length < 2 ? "Typ om te zoeken" : `${insight.filteredResults.length} resultaat${insight.filteredResults.length === 1 ? "" : "en"}`}</h2>
            <p className="muted">{insight.activeModule === "alles" ? "Over alle modules." : `Gefilterd op ${insight.activeModule}.`}</p>
          </div>
          <div className="today-stack">
            <Metric label="Totaal" value={insight.results.length} />
            <Metric label="Modules" value={insight.moduleCounts.length} />
            <Metric label="Actieve filter" value={insight.activeModule === "alles" ? "Alles" : insight.activeModule} />
          </div>
        </aside>
      </section>

      <section className="search-control card">
        <div className="search-control-main">
          <span className="summary-icon">
            <Compass size={18} />
          </span>
          <div>
            <span className="eyebrow">Zoekregie</span>
            <h2>{insight.trimmedQuery.length < 2 ? "Begin met zoeken" : insight.bestResult ? `Beste route: ${insight.bestResult.module}` : "Geen directe match"}</h2>
            <p className="muted">{insight.searchState}</p>
          </div>
        </div>
        <div className="search-control-grid">
          <SearchControlMetric label="Beste match" value={insight.bestResult?.title ?? "Geen"} detail={insight.bestResult?.meta || insight.bestResult?.module || "Nog geen resultaat"} />
          <SearchControlMetric label="Topmodule" value={insight.dominantModule?.module ?? "Geen"} detail={insight.dominantModule ? `${insight.dominantModule.count} resultaat${insight.dominantModule.count === 1 ? "" : "en"}` : "Geen verdeling"} />
          <SearchControlMetric label="Exact" value={insight.exactTitleMatches} detail="Titelmatches" />
          <SearchControlMetric label="Afgeschermd" value={insight.maskedResults} detail="Gemaskeerde resultaten" />
          <SearchControlMetric label="Kwaliteit" value={`${insight.score}/${insight.totalChecks}`} detail={`${insight.percent}% op orde`} />
        </div>
        <div className="search-control-actions">
          {insight.bestResult ? (
            <Link className="button primary" href={insight.bestResult.href}>
              Open beste match <ArrowRight size={16} />
            </Link>
          ) : (
            <Link className="button" href="/snel">Snel toevoegen</Link>
          )}
          <span className="status">
            <ShieldCheck size={14} /> Gevoelige waarden gemaskeerd
          </span>
        </div>
        <div className="search-action-grid">
          {insight.actions.map((action) => (
            <Link className={action.done ? "search-action done" : "search-action"} href={action.href} key={action.id}>
              <span>{action.done ? "Op orde" : "Actie"}</span>
              <strong>{action.title}</strong>
              <small>{action.detail}</small>
            </Link>
          ))}
        </div>
      </section>

      <section className="search-dashboard" style={{ marginTop: 22 }}>
        <aside className="card search-filter-card">
          <div className="section-head">
            <div>
              <span className="eyebrow">Filters</span>
              <h2>Modules</h2>
            </div>
            <span className="summary-icon"><Filter size={18} /></span>
          </div>
          <div className="search-filter-list">
            <SearchFilterLink label="Alles" count={insight.results.length} query={query} active={insight.activeModule === "alles"} />
            {insight.moduleCounts.map(({ module, count }) => (
              <SearchFilterLink label={module} count={count} query={query} active={insight.activeModule === module} key={module} />
            ))}
          </div>
          <div className="search-safe-note">
            Gevoelige document- en huisinfowaarden worden in zoekresultaten gemaskeerd.
          </div>
        </aside>

        <div className="grid">
          {insight.trimmedQuery.length < 2 ? (
            <div className="card empty-state">Typ minimaal twee tekens om te zoeken.</div>
          ) : insight.filteredResults.length === 0 ? (
            <div className="card empty-state">Geen resultaten gevonden.</div>
          ) : (
            Object.entries(insight.groupedResults).map(([module, moduleResults]) => (
              <div className="card search-result-card" key={module}>
                <div className="section-head">
                  <div>
                    <h2>{module}</h2>
                    <p className="muted">{moduleResults.length} resultaat{moduleResults.length === 1 ? "" : "en"}</p>
                  </div>
                  <span className="status">{moduleResults.length}</span>
                </div>
                <ul className="list">
                  {moduleResults.map((result) => (
                    <li className="list-row search-result-row" key={result.id}>
                      <div className="row-main">
                        <span className="search-result-module">{result.module}</span>
                        <div className="row-title">{result.title}</div>
                        <div className="row-meta">
                          {[result.meta || module, result.privacy === "masked" ? "Afgeschermd" : null].filter(Boolean).join(" · ")}
                        </div>
                        {result.detail && <div className="row-description">{result.detail}</div>}
                      </div>
                      <Link className="status" href={result.href}>
                        Open <ArrowRight size={14} />
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
        <aside className="card search-tips-card">
          <h2>Zoektips</h2>
          <p className="muted">Probeer namen, categorieen, datums, leveranciers, locaties of bedragen. Gebruik modulefilters als je veel resultaten krijgt.</p>
        </aside>
      </section>
    </AppShell>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="today-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SearchControlMetric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="search-control-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function SearchFilterLink({ label, count, query, active }: { label: string; count: number; query: string; active: boolean }) {
  const moduleParam = label === "Alles" ? "" : `&module=${encodeURIComponent(label)}`;
  return (
    <Link className={active ? "active" : ""} href={`/zoeken?q=${encodeURIComponent(query)}${moduleParam}`}>
      <span>{label}</span>
      <strong>{count}</strong>
    </Link>
  );
}
