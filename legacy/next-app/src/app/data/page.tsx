import Link from "next/link";
import { redirect } from "next/navigation";
import { Archive, CheckCircle2, ClipboardList, Database, Download, FileJson, HardDriveDownload, KeyRound, RotateCcw, Server, ServerCog, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { buildDataGovernanceInsight } from "@/lib/data-governance";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { buildEnvironmentReadiness } from "@/lib/environment-readiness";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function DataPage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <DataContent data={await getLocalAppData()} localMode />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <DataContent data={data} />;
}

function DataContent({ data, localMode = false }: { data: AppData; localMode?: boolean }) {
  const insight = buildDataGovernanceInsight(data);
  const environment = buildEnvironmentReadiness();

  return (
    <AppShell>
      <section className="dashboard-hero">
        <div className="hero-panel">
          <span className="eyebrow">Beheer</span>
          <h1>Data & backup</h1>
          <p className="hero-copy">
            Bekijk hoeveel gezinsdata is opgeslagen en download een JSON-export voor eigen archief of migratie.
          </p>
          <div className="quick-actions">
            <a className="button primary" href="/api/export">
              <Download size={17} /> Export downloaden
            </a>
            <Link className="button" href="/inrichting">Inrichting bekijken</Link>
            <Link className="button" href="/instellingen">Instellingen</Link>
          </div>
        </div>
        <aside className="today-panel">
          <div>
            <span className="eyebrow">Opslag</span>
            <h2 style={{ margin: "8px 0 0" }}>{localMode ? "Lokale database" : "Database"}</h2>
            <p className="muted">Export bevat geen Home Assistant, Hue, Google of bank API tokens.</p>
          </div>
          <div className="today-stack">
            <Metric label="Records" value={insight.totalRecords} />
            <Metric label="Modules" value={insight.activeModuleCount} />
            <Metric label="Koppelingen" value={insight.activeIntegrations} />
          </div>
        </aside>
      </section>

      <section className="data-control card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Dataregie</span>
            <h2>Privacy, backup en koppelingen</h2>
            <p className="muted">Een beheerbeeld voor wat lokaal opgeslagen is en wat extra aandacht verdient.</p>
          </div>
          <span className="summary-icon">
            <ShieldCheck size={18} />
          </span>
        </div>
        <div className="data-control-grid">
          <DataMetric icon={<Server size={17} />} label="Opslaglocatie" value={localMode ? "Postgres" : "Database"} detail={localMode ? "Onder eigen beheer geconfigureerd" : "Via geconfigureerde backend"} />
          <DataMetric icon={<KeyRound size={17} />} label="Gevoelige items" value={insight.sensitiveTotal} detail={`${insight.sensitiveDocuments} documenten, ${insight.sensitiveInfo} huisinfo`} />
          <DataMetric icon={<Archive size={17} />} label="Exportdekking" value={`${insight.backupScore}/${insight.backupTotal}`} detail="JSON backup v3 met samenvatting" />
          <DataMetric icon={<Database size={17} />} label="Nooddata" value={insight.emergencyContacts} detail="Contacten met noodprioriteit" />
        </div>
        <div className="data-backup-row">
          <div>
            <strong>{insight.nextAction ? insight.nextAction.title : "Backupgereedheid op orde"}</strong>
            <p className="muted">{insight.nextAction ? insight.nextAction.detail : "Exports bevatten recordtellingen, huishoudvoorkeuren en appdata; secret-achtige velden worden automatisch afgeschermd."}</p>
          </div>
          <div className="data-backup-actions">
            <span className="status">{insight.backupPercent}%</span>
            {insight.nextAction && <Link className="button" href={insight.nextAction.href}>Open actie</Link>}
            <a className="button primary" href="/api/export">
              <Download size={17} /> Download
            </a>
          </div>
        </div>
        <div className="data-backup-checklist">
          {insight.backupActions.map((item) => (
            <Link className={item.done ? "data-backup-check done" : "data-backup-check"} href={item.href} key={item.id}>
              <span>{item.done ? "OK" : "Actie"}</span>
              <strong>{item.title}</strong>
              <small>{item.detail}</small>
            </Link>
          ))}
        </div>
      </section>

      <section className="grid two-col" style={{ marginTop: 22 }}>
        <div className="card module-card">
          <div className="section-head">
            <div>
              <h2>Data-overzicht</h2>
              <p className="muted">Aantal records per onderdeel.</p>
            </div>
            <span className="summary-icon">
              <Database size={18} />
            </span>
          </div>
          <div className="data-count-grid">
            {insight.counts.map((item) => (
              <div className="data-count" key={item.key}>
                <span>{item.label}</span>
                <strong>{item.count}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="grid">
          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Omgeving</h2>
                <p className="muted">Parity tussen lokale dev, VPS en integraties zonder secrets te tonen.</p>
              </div>
              <span className="summary-icon">
                <ServerCog size={18} />
              </span>
            </div>
            <div className="environment-summary compact">
              <div>
                <strong>{environment.modeLabel}</strong>
                <span>{environment.requiredReady}/{environment.requiredTotal} verplicht klaar · {environment.optionalReady}/{environment.optionalTotal} optioneel compleet</span>
              </div>
              <div className="setup-bar" aria-hidden="true">
                <span style={{ width: `${environment.readyPercent}%` }} />
              </div>
            </div>
            <div className="environment-grid compact">
              {environment.groups.map((group) => (
                <div className={group.ready ? "environment-group ready" : group.configured > 0 ? "environment-group partial" : "environment-group"} key={group.id}>
                  <div>
                    <strong>{group.title}</strong>
                    <span>{group.configured}/{group.total} aanwezig</span>
                  </div>
                  <span className={group.ready ? "status" : group.configured > 0 ? "status accent" : "status muted-status"}>
                    {group.ready ? <CheckCircle2 size={14} /> : null}
                    {group.ready ? "Klaar" : group.configured > 0 ? "Deels" : "Leeg"}
                  </span>
                </div>
              ))}
            </div>
            {environment.nextAction && (
              <div className="data-backup-note neutral-note">
                <KeyRound size={17} />
                <p>
                  Volgende parity-stap: vul {environment.nextAction.title.toLowerCase()} aan. Waarden blijven server-side en worden hier niet getoond.
                </p>
              </div>
            )}
          </div>

          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Databasebackup</h2>
                <p className="muted">JSON-export is handig voor migratie; een Postgres dump is je echte herstelbestand.</p>
              </div>
              <span className="summary-icon">
                <HardDriveDownload size={18} />
              </span>
            </div>
            <div className="backup-command-grid">
              <BackupCommand
                title={localMode ? "Lokale dev database" : "Database dump"}
                detail="Maakt een compact Postgres herstelbestand van de database die in DATABASE_URL staat."
                command={'pg_dump "$DATABASE_URL" --format=custom --file family-app-$(date +%F).dump'}
              />
              <BackupCommand
                title="VPS via Docker Compose"
                detail="Uit te voeren vanaf je Mac wanneer de VPS compose-stack draait in /opt/family-app."
                command={"ssh clubtooladmin@app.example.com 'cd /opt/family-app && docker compose exec -T db pg_dump -U family_app -d family_app --format=custom' > family-app-$(date +%F).dump"}
              />
            </div>
            <div className="data-backup-note">
              <ClipboardList size={17} />
              <p>
                Bewaar database dumps buiten de VPS, bijvoorbeeld op een versleutelde schijf of password manager vault.
                Test later ook een restore-flow voordat je volledig op productie gaat vertrouwen.
              </p>
            </div>
          </div>

          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Koppelingen</h2>
                <p className="muted">Status van externe diensten en wat de export bevat.</p>
              </div>
              <span className="summary-icon">
                <KeyRound size={18} />
              </span>
            </div>
            <div className="data-integration-list">
              {insight.integrations.map((item) => (
                <div className="data-integration-row" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.active ? "Geconfigureerd" : "Niet actief"}</strong>
                </div>
              ))}
            </div>
            <p className="muted" style={{ margin: 0 }}>
              Exports bevatten configuratiestatus en metadata, maar geen server-side tokens, secrets of wachtwoordhashes.
            </p>
          </div>

          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Export</h2>
                <p className="muted">Download een leesbare JSON-backup van het huishouden.</p>
              </div>
              <span className="summary-icon">
                <FileJson size={18} />
              </span>
            </div>
            <ul className="list">
              <li className="list-row">
                <div className="row-main">
                  <div className="row-title">Exportformaat v3</div>
                  <div className="row-description">Inclusief metadata, recordtellingen, huishoudvoorkeuren en alle gezinsmodules die via de appdata beschikbaar zijn.</div>
                </div>
              </li>
              <li className="list-row">
                <div className="row-main">
                  <div className="row-title">Secrets afgeschermd</div>
                  <div className="row-description">Velden met token, secret, wachtwoord, sessie of API key in de naam worden automatisch vervangen door [afgeschermd].</div>
                </div>
              </li>
              <li className="list-row">
                <div className="row-main">
                  <div className="row-title">Herstelpad</div>
                  <div className="row-description">Import/herstel is nog bewust handmatig; deze export is bedoeld als veilig archief en migratiebasis.</div>
                </div>
                <span className="status">Handmatig</span>
              </li>
            </ul>
            <a className="button primary" href="/api/export">
              <Download size={17} /> JSON export downloaden
            </a>
          </div>

          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Dataprincipes</h2>
                <p className="muted">Past bij lokaal draaien op je VPS.</p>
              </div>
              <span className="summary-icon">
                <ShieldCheck size={18} />
              </span>
            </div>
            <ul className="list">
              <li className="list-row">
                <div className="row-main">
                  <div className="row-title">Lokaal als primaire bron</div>
                  <div className="row-description">De productieapp gebruikt de Postgres database op de VPS als bron voor gezinsdata.</div>
                </div>
              </li>
              <li className="list-row">
                <div className="row-main">
                  <div className="row-title">Gevoelige gegevens zichtbaar labelen</div>
                  <div className="row-description">Documenten en huisinfo met gevoelige inhoud worden gemarkeerd in de app en gemaskeerd in globale zoekresultaten.</div>
                </div>
              </li>
              <li className="list-row">
                <div className="row-main">
                  <div className="row-title">Bewust exporteren</div>
                  <div className="row-description">Exports zijn handmatig en vereisen een ingelogde sessie.</div>
                </div>
              </li>
              <li className="list-row">
                <div className="row-main">
                  <div className="row-title">Herstel later automatiseren</div>
                  <div className="row-description">De export bevat nu genoeg metadata om later een gecontroleerde import- en restoreflow te bouwen.</div>
                </div>
                <span className="summary-icon">
                  <RotateCcw size={17} />
                </span>
              </li>
            </ul>
          </div>
        </div>
      </section>
    </AppShell>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="today-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DataMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="data-metric">
      <span className="data-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function BackupCommand({ title, detail, command }: { title: string; detail: string; command: string }) {
  return (
    <div className="backup-command">
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
      <code>{command}</code>
    </div>
  );
}
