import Link from "next/link";
import { redirect } from "next/navigation";
import { AlertTriangle, CheckCircle2, Circle, ClipboardCheck, Gauge, PackagePlus } from "lucide-react";
import { applyStarterPack } from "@/app/actions";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { buildSetupOverview, type SetupStep } from "@/lib/setup";
import { buildStarterPackSummary } from "@/lib/starter-pack";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function SetupPage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <SetupContent data={await getLocalAppData()} localMode />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <SetupContent data={data} />;
}

function SetupContent({ data, localMode = false }: { data: AppData; localMode?: boolean }) {
  const overview = buildSetupOverview(data);
  const starterSummary = buildStarterPackSummary();

  return (
    <AppShell>
      <section className="dashboard-hero">
        <div className="hero-panel">
          <span className="eyebrow">App inrichten</span>
          <h1>Inrichting</h1>
          <p className="hero-copy">
            Een praktische checklist om de gezinsapp volledig te vullen: accounts, dagelijkse routines, planning, huisinfo en koppelingen.
          </p>
          <div className="setup-progress" aria-label={`Voortgang ${overview.progress.percent} procent`}>
            <div>
              <strong>{overview.progress.percent}% compleet</strong>
              <span>{overview.progress.done} van {overview.progress.total} onderdelen klaar</span>
            </div>
            <div className="setup-bar">
              <span style={{ width: `${overview.progress.percent}%` }} />
            </div>
          </div>
        </div>
        <aside className="today-panel">
          <div>
            <span className="eyebrow">Volgende stappen</span>
            <h2 style={{ margin: "8px 0 0" }}>{overview.nextSteps.length === 0 ? "Alles gevuld" : `${overview.nextSteps.length} suggesties`}</h2>
            <p className="muted">Pak eerst de onderdelen die de meeste waarde geven.</p>
          </div>
          <div className="today-stack">
            {overview.nextSteps.length === 0 ? (
              <div className="today-row">
                <span>Checklist</span>
                <strong>OK</strong>
              </div>
            ) : (
              overview.nextSteps.slice(0, 3).map((step) => (
                <Link className="today-row setup-next-link" href={step.href} key={step.id}>
                  <span>{step.title}</span>
                  <strong>Open</strong>
                </Link>
              ))
            )}
          </div>
        </aside>
      </section>

      {localMode && overview.progress.percent < 70 && (
        <section className="setup-starter card">
          <div className="section-head">
            <div>
              <span className="eyebrow">Versnellen</span>
              <h2>Starterpakket</h2>
              <p className="muted">Vul in een keer basisroutines, terugkerende boodschappen, budgetten, huisinfo en documenten. Bestaande items worden niet dubbel aangemaakt.</p>
            </div>
            <span className="summary-icon">
              <PackagePlus size={18} />
            </span>
          </div>
          <form action={applyStarterPack} className="setup-starter-row">
            <div>
              <strong>Gebruik dit als startpunt en pas daarna bedragen, telefoonnummers en bewaarplekken aan.</strong>
              <p className="muted">Er worden {starterSummary.totalItems} voorbeelditems toegevoegd, maar geen externe koppelingen, wachtwoorden of echte bankdata.</p>
            </div>
            <button className="button primary">Starterpakket toevoegen</button>
          </form>
          <div className="starter-summary-grid" aria-label="Inhoud van het starterpakket">
            {starterSummary.modules.map((module) => (
              <Link className="starter-summary-item" href={module.href} key={module.id}>
                <span>{module.label}</span>
                <strong>{module.count}</strong>
              </Link>
            ))}
          </div>
          <div className="starter-next-edits">
            {starterSummary.nextEdits.map((edit) => (
              <Link className="starter-next-edit" href={edit.href} key={edit.title}>
                <strong>{edit.title}</strong>
                <small>{edit.detail}</small>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section className="setup-control card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Inrichtingsregie</span>
            <h2>Waar zit de meeste winst?</h2>
            <p className="muted">Voortgang per domein en de open stappen die direct dagelijks verschil maken.</p>
          </div>
          <span className="summary-icon">
            <Gauge size={18} />
          </span>
        </div>
        <div className="setup-control-grid">
          <SetupMetric label="Totaal klaar" value={`${overview.progress.done}/${overview.progress.total}`} detail={`${overview.progress.percent}% afgerond`} />
          <SetupMetric label="Zwakste domein" value={overview.weakestGroup?.group ?? "OK"} detail={overview.weakestGroup ? `${overview.weakestGroup.percent}% klaar` : "Geen stappen"} />
          <SetupMetric label="Hoge impact open" value={overview.highImpactOpen.length} detail={overview.highImpactOpen[0]?.title ?? "Geen kritieke open punten"} />
          <SetupMetric label="Koppelingen" value={overview.grouped.Koppelingen?.filter((step) => step.done).length ?? 0} detail={`${overview.grouped.Koppelingen?.length ?? 0} stappen totaal`} />
        </div>
        <div className="setup-domain-grid">
          {overview.groupProgress.map((item) => (
            <Link className="setup-domain" href={overview.grouped[item.group as SetupStep["group"]]?.find((step) => !step.done)?.href ?? "/inrichting"} key={item.group}>
              <div>
                <strong>{item.group}</strong>
                <span>{item.done} van {item.total} klaar</span>
              </div>
              <div className="setup-bar" aria-hidden="true">
                <span style={{ width: `${item.percent}%` }} />
              </div>
            </Link>
          ))}
        </div>
        {overview.nextAction && (
          <div className="setup-next-action">
            <div>
              <strong>{overview.nextAction.title}</strong>
              <p className="muted">{overview.nextAction.detail}</p>
            </div>
            <Link className="button primary" href={overview.nextAction.href}>Nu aanvullen</Link>
          </div>
        )}
        {overview.highImpactOpen.length > 0 && (
          <div className="setup-focus-list">
            <div className="row-title">
              <AlertTriangle size={17} />
              Eerst oppakken
            </div>
            <div className="tag-list">
              {overview.highImpactOpen.map((step) => (
                <Link className="tag setup-focus-tag" href={step.href} key={step.id}>{step.title}</Link>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="grid setup-grid section-stack">
        {Object.entries(overview.grouped).map(([group, groupSteps]) => (
          <div className="card module-card" key={group}>
            <div className="section-head">
              <div>
                <h2>{group}</h2>
                <p className="muted">{groupSteps.filter((step) => step.done).length} van {groupSteps.length} klaar</p>
              </div>
              <span className="summary-icon">
                <ClipboardCheck size={18} />
              </span>
            </div>
            <ul className="list">
              {groupSteps.map((step) => (
                <li className={`list-row setup-step ${step.done ? "done" : "open"}`} key={step.id}>
                  <div className="row-main">
                    <div className="row-title">
                      {step.done ? <CheckCircle2 size={17} /> : <Circle size={17} />}
                      <span>{step.title}</span>
                    </div>
                    <div className="row-description">{step.detail}</div>
                  </div>
                  <Link className={step.done ? "status" : "status accent"} href={step.href}>
                    {step.done ? "Bekijken" : "Aanvullen"}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </AppShell>
  );
}

function SetupMetric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="setup-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
