import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Bell, CalendarDays, CheckCircle2, Clock, Copy, KeyRound, LayoutDashboard, Link2, LogOut, Mail, Moon, ServerCog, ShieldCheck, ShoppingCart, UserRound, UsersRound } from "lucide-react";
import { changePassword, createInvite, removeMember, revokeInvite, revokeOtherSessions, updateHouseholdPreferences, updateMemberRole, updateProfile } from "@/app/actions";
import { AppShell } from "@/components/app-shell";
import { BunqSyncActions } from "@/components/bunq-actions";
import { DemoWorkspace } from "@/components/demo-workspace";
import {
  BunqConnectionForm,
  GoogleHomeForm,
  HomeAssistantForm,
  HueConfigForm,
  OutlookCalendarForm,
  TaskIntegrationForm,
} from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { PasswordInput } from "@/components/password-input";
import { buildAccessReadiness } from "@/lib/access-readiness";
import { getLocalAppData, getLocalInvites } from "@/lib/local-db";
import { getLocalSessionOverviewForCurrentUser, getLocalUser } from "@/lib/local-auth";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { buildEnvironmentReadiness, type EnvironmentReadiness } from "@/lib/environment-readiness";
import { dateKey, dateSortValue } from "@/lib/date-keys";
import { memberName, shortDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function SettingsPage({ searchParams }: { searchParams?: Promise<{ bunq_status?: string; bunq_error?: string }> }) {
  const origin = await requestOrigin();
  const params = await searchParams;
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return (
      <SettingsContent
        data={await getLocalAppData()}
        invites={await getLocalInvites()}
        sessions={(await getLocalSessionOverviewForCurrentUser()) ?? []}
        localMode
        currentUserId={user.id}
        origin={origin}
        environment={buildEnvironmentReadiness()}
        bunqStatus={params?.bunq_status}
        bunqError={params?.bunq_error}
      />
    );
  }
  return <DemoWorkspace view="instellingen" />;
}

function SettingsContent({
  data,
  invites,
  sessions,
  localMode = false,
  currentUserId,
  origin,
  environment,
  bunqStatus,
  bunqError,
}: {
  data: Awaited<ReturnType<typeof getLocalAppData>>;
  invites: Array<{ id: string; code: string; expires_at?: string; created_at?: string }>;
  sessions: Array<{ id: string; created_at: string; last_seen_at: string; expires_at: string; is_current: boolean }>;
  localMode?: boolean;
  currentUserId?: string;
  origin: string;
  environment: EnvironmentReadiness;
  bunqStatus?: string;
  bunqError?: string;
}) {
  const currentMember = data.members.find((member) => member.user_id === currentUserId);
  const canManageMembers = localMode && currentMember?.role === "owner";
  const currentProfile = currentMember?.profile;
  const accessReadiness = buildAccessReadiness(data, invites, sessions, currentUserId);

  return (
    <AppShell>
      <section className="grid two-col">
        <div className="grid">
          <div>
            <h1>Instellingen</h1>
            <p className="muted">Beheer gezinsleden, uitnodigingen en integraties.</p>
          </div>
          {bunqStatus === "oauth_gekoppeld" && (
            <div className="success">bunq OAuth is gekoppeld. De access token is server-side opgeslagen; sessie/sync is de volgende stap.</div>
          )}
          {bunqError && <div className="error">bunq OAuth: {bunqError}</div>}
          <section className="settings-control card">
            <div className="section-head">
              <div>
                <span className="eyebrow">Toegang</span>
                <h2>Huishoudenstatus</h2>
                <p className="muted">Account, rollen en meldingen in een compact beheerbeeld.</p>
              </div>
              <span className="summary-icon">
                <ShieldCheck size={18} />
              </span>
            </div>
            <div className="settings-control-grid">
              <SettingsStatus icon={<UsersRound size={17} />} label="Gezinsleden" value={data.members.length} detail={`${accessReadiness.admins} beheerder${accessReadiness.admins === 1 ? "" : "s"}`} />
              <SettingsStatus icon={<KeyRound size={17} />} label="Open invites" value={invites.length} detail={invites.length > 0 ? "Deel of trek codes in" : "Geen open toegangscodes"} />
              <SettingsStatus icon={<UserRound size={17} />} label="Profielen compleet" value={`${data.members.length - accessReadiness.incompleteProfiles}/${data.members.length}`} detail={accessReadiness.incompleteProfiles === 0 ? "Alle profielen gevuld" : `${accessReadiness.incompleteProfiles} profiel${accessReadiness.incompleteProfiles === 1 ? "" : "en"} mist info`} />
              <SettingsStatus icon={<Bell size={17} />} label="Meldingen" value={accessReadiness.emailNotifications} detail="Leden met e-mailmeldingen aan" />
            </div>
            <div className="settings-readiness">
              <div>
                <strong>{accessReadiness.nextAction ? accessReadiness.nextAction.title : "Inrichting toegang op orde"}</strong>
                <span>{accessReadiness.score}/{accessReadiness.total} aandachtspunten op orde</span>
              </div>
              <div className="setup-bar" aria-hidden="true">
                <span style={{ width: `${accessReadiness.percent}%` }} />
              </div>
            </div>
            <div className="settings-action-grid">
              {accessReadiness.actions.map((action) => (
                <Link className={action.done ? "settings-action done" : "settings-action"} href={action.href} key={action.id}>
                  <span>{action.done ? "OK" : "Actie"}</span>
                  <strong>{action.title}</strong>
                  <small>{action.detail}</small>
                </Link>
              ))}
            </div>
          </section>
          {localMode && currentProfile && (
            <>
              <div className="card">
                <div className="section-head">
                  <div>
                    <h2>Mijn profiel</h2>
                    <p className="muted">Deze gegevens worden in je eigen database bewaard.</p>
                  </div>
                  <span className="status">{currentMember?.role ?? "lid"}</span>
                </div>
                <form className="form" action={updateProfile}>
                  <div className="profile-preview">
                    <Avatar color={currentProfile.avatar_color} name={currentProfile.full_name ?? currentProfile.email ?? "Ik"} />
                    <div>
                      <strong>{currentProfile.full_name ?? "Naam nog niet ingesteld"}</strong>
                      <p className="muted">{currentProfile.email}</p>
                    </div>
                  </div>
                  <div className="field">
                    <label htmlFor="profile-name">Naam</label>
                    <input id="profile-name" name="full_name" defaultValue={currentProfile.full_name ?? ""} />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-email">E-mail</label>
                    <input id="profile-email" name="email" type="email" required defaultValue={currentProfile.email ?? ""} />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-phone">Telefoon</label>
                    <input id="profile-phone" name="phone" type="tel" defaultValue={currentProfile.phone ?? ""} />
                  </div>
                  <div className="field">
                    <label htmlFor="profile-color">Kleur</label>
                    <select id="profile-color" name="avatar_color" defaultValue={currentProfile.avatar_color ?? "groen"}>
                      <option value="groen">Groen</option>
                      <option value="blauw">Blauw</option>
                      <option value="oranje">Oranje</option>
                      <option value="paars">Paars</option>
                      <option value="grijs">Grijs</option>
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="profile-digest-time">Dagoverzicht</label>
                    <select id="profile-digest-time" name="digest_time" defaultValue={currentProfile.digest_time ?? "07:30"}>
                      <option value="">Geen dagoverzicht</option>
                      <option value="07:00">07:00</option>
                      <option value="07:30">07:30</option>
                      <option value="08:00">08:00</option>
                      <option value="19:00">19:00</option>
                    </select>
                  </div>
                  <label className="check-row">
                    <input type="checkbox" name="notification_email" defaultChecked={currentProfile.notification_email !== false} />
                    E-mailmeldingen ontvangen
                  </label>
                  <button className="button primary">Profiel opslaan</button>
                </form>
              </div>
              <HouseholdPreferencesPanel data={data} />
              <NotificationsPanel data={data} currentUserId={currentUserId} />
            </>
          )}
          {localMode && (
            <SecurityPanel sessions={sessions} />
          )}
          <div className="card">
            <div className="section-head">
              <div>
                <h2>Gezinsleden</h2>
                <p className="muted">Rollen en toegang voor dit huishouden.</p>
              </div>
              <span className="status">{data.members.length} leden</span>
            </div>
            <ul className="list">
              {data.members.map((member) => (
                <li className="list-row" key={member.user_id}>
                  <div className="member-identity">
                    <Avatar color={member.profile?.avatar_color} name={member.profile?.full_name ?? member.profile?.email ?? "Gezinslid"} />
                    <div>
                      <div className="row-title">{member.profile?.full_name ?? member.profile?.email ?? "Gezinslid"}</div>
                      <div className="row-meta">
                        {roleLabel(member.role)}{member.profile?.email ? ` · ${member.profile.email}` : ""}
                      </div>
                    </div>
                  </div>
                  {canManageMembers && member.user_id !== currentUserId && member.role !== "owner" && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      <form action={updateMemberRole} style={{ display: "flex", gap: 8 }}>
                        <input type="hidden" name="user_id" value={member.user_id} />
                        <select name="role" defaultValue={member.role} aria-label="Rol">
                          <option value="member">Lid</option>
                          <option value="admin">Beheerder</option>
                        </select>
                        <button className="button">Rol opslaan</button>
                      </form>
                      <form action={removeMember}>
                        <input type="hidden" name="user_id" value={member.user_id} />
                        <button className="button danger">Verwijderen</button>
                      </form>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
          <InvitesPanel invites={invites} origin={origin} localMode={localMode} canCreate={localMode ? currentMember?.role === "owner" || currentMember?.role === "admin" : true} />
        </div>
        <div className="grid">
          <EnvironmentReadinessCard readiness={environment} />
          <ModuleSubmenu title="Home Assistant koppelen" detail="Base URL en token veilig opslaan">
            <HomeAssistantForm />
          </ModuleSubmenu>
          <ModuleSubmenu title="Hue koppelen" detail="Bridge-adres en token beheren">
            <HueConfigForm />
          </ModuleSubmenu>
          <ModuleSubmenu title="Google Home koppelen" detail="Google/Nest-integratie voorbereiden">
            <GoogleHomeForm />
          </ModuleSubmenu>
          <ModuleSubmenu title="Outlook agenda koppelen" detail="Gezinsagenda met Outlook verbinden">
            <OutlookCalendarForm />
          </ModuleSubmenu>
          <ModuleSubmenu title="Bunq koppelen" detail="Bankkoppeling voor saldo en transacties">
            <BunqConnectionForm />
          </ModuleSubmenu>
          <BunqConnectionStatus data={data} />
          <ModuleSubmenu title="Takenkoppeling instellen" detail="Apple herinneringen of Microsoft To Do voorbereiden">
            <TaskIntegrationForm />
          </ModuleSubmenu>
        </div>
      </section>
    </AppShell>
  );
}

function BunqConnectionStatus({ data }: { data: Awaited<ReturnType<typeof getLocalAppData>> }) {
  const connections = data.bankConnections.filter((connection) => connection.provider === "bunq");
  const latest = connections[0] ?? null;

  return (
    <div className="card bunq-status-card">
      <div className="section-head">
        <div>
          <h2>bunq status</h2>
          <p className="muted">De API key wordt afgeschermd opgeslagen; hij wordt hier nooit terug getoond.</p>
        </div>
        <span className={latest ? "status accent" : "status muted-status"}>
          {latest?.oauth_connected_at ? "OAuth gekoppeld" : latest ? statusLabel(latest.status) : "Niet gekoppeld"}
        </span>
      </div>
      {latest ? (
        <div className="grid">
          <ul className="list">
            {connections.map((connection) => (
              <li className="list-row" key={connection.id}>
                <div>
                  <div className="row-title">bunq {connection.environment}</div>
                  <div className="row-meta">
                    {connection.oauth_connected_at ? "OAuth token opgeslagen" : connection.oauth_client_id ? "OAuth client ingesteld" : "API key opgeslagen"} ·{" "}
                    {statusLabel(connection.status)} · laatst gesynchroniseerd {shortDate(connection.last_sync_at)}
                  </div>
                  {connection.oauth_connected_at ? (
                    <div className="row-description">
                      OAuth autorisatie is afgerond. De volgende stap is een bunq sessie maken met dit access token en daarna rekeningen/transacties ophalen.
                    </div>
                  ) : connection.oauth_client_id ? (
                    <div className="row-description">
                      OAuth clientgegevens zijn opgeslagen. Klik op autoriseren om bunq toestemming te geven via je bunq app.
                    </div>
                  ) : connection.status === "needs_session" && (
                    <div className="row-description">
                      De key staat in de database. Voor live saldo/transacties mist nog de bunq installation/device/session en request-signing stap.
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {latest.oauth_client_id && (
            <a className="button primary" href="/api/bunq/oauth/start">
              bunq autoriseren
            </a>
          )}
          <BunqSyncActions />
        </div>
      ) : (
        <div className="grid">
          <p className="empty-state">Nog geen bunq API key opgeslagen.</p>
          <BunqSyncActions disabled />
        </div>
      )}
    </div>
  );
}

function EnvironmentReadinessCard({ readiness }: { readiness: EnvironmentReadiness }) {
  return (
    <div className="card environment-control">
      <div className="section-head">
        <div>
          <span className="eyebrow">Dev parity</span>
          <h2>Omgeving</h2>
          <p className="muted">Controleer welke lokale/VPS variabelen aanwezig zijn zonder secrets te tonen.</p>
        </div>
        <span className="summary-icon">
          <ServerCog size={18} />
        </span>
      </div>
      <div className="environment-summary">
        <div>
          <strong>{readiness.modeLabel}</strong>
          <span>{readiness.requiredReady}/{readiness.requiredTotal} verplichte groepen klaar · {readiness.optionalReady}/{readiness.optionalTotal} optioneel compleet</span>
        </div>
        <div className="setup-bar" aria-hidden="true">
          <span style={{ width: `${readiness.readyPercent}%` }} />
        </div>
      </div>
      {readiness.nextAction && (
        <div className="environment-next">
          <KeyRound size={17} />
          <div>
            <strong>{readiness.nextAction.title} aanvullen</strong>
            <span>{readiness.nextAction.description}</span>
          </div>
        </div>
      )}
      <div className="environment-grid">
        {readiness.groups.map((group) => (
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
    </div>
  );
}

function statusLabel(status: string) {
  if (status === "configured") return "Gekoppeld";
  if (status === "needs_session") return "Sessie nodig";
  if (status === "sync_error") return "Syncfout";
  if (status === "needs_auth") return "Autorisatie nodig";
  return status;
}

function HouseholdPreferencesPanel({ data }: { data: Awaited<ReturnType<typeof getLocalAppData>> }) {
  const preferences = data.householdPreferences;
  const store = preferences.default_shopping_store?.trim() || "Geen standaardwinkel";
  const quietHours = preferences.quiet_hours_start && preferences.quiet_hours_end
    ? `${preferences.quiet_hours_start} - ${preferences.quiet_hours_end}`
    : "Niet ingesteld";

  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Huishoudvoorkeuren</h2>
          <p className="muted">Standaarden die de gezinsmodules als uitgangspunt gebruiken.</p>
        </div>
        <span className="summary-icon">
          <LayoutDashboard size={18} />
        </span>
      </div>
      <div className="settings-metrics">
        <div className="settings-metric">
          <CalendarDays size={17} />
          <div>
            <strong>{preferences.week_starts_on === "sunday" ? "Zondag" : "Maandag"}</strong>
            <span>Start van de week</span>
          </div>
        </div>
        <div className="settings-metric">
          <ShoppingCart size={17} />
          <div>
            <strong>{store}</strong>
            <span>Boodschappen</span>
          </div>
        </div>
        <div className="settings-metric">
          <LayoutDashboard size={17} />
          <div>
            <strong>{dashboardLabel(preferences.default_dashboard)}</strong>
            <span>Standaard startbeeld</span>
          </div>
        </div>
        <div className="settings-metric">
          <Moon size={17} />
          <div>
            <strong>{quietHours}</strong>
            <span>Stille uren</span>
          </div>
        </div>
      </div>
      <form className="form preference-form" action={updateHouseholdPreferences}>
        <div className="field">
          <label htmlFor="week-start">Week begint op</label>
          <select id="week-start" name="week_starts_on" defaultValue={preferences.week_starts_on}>
            <option value="monday">Maandag</option>
            <option value="sunday">Zondag</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="default-dashboard">Startbeeld</label>
          <select id="default-dashboard" name="default_dashboard" defaultValue={preferences.default_dashboard}>
            <option value="vandaag">Vandaag</option>
            <option value="compact">Compact dashboard</option>
            <option value="uitgebreid">Uitgebreid dashboard</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="default-shopping-store">Standaard winkel</label>
          <input id="default-shopping-store" name="default_shopping_store" defaultValue={preferences.default_shopping_store ?? ""} placeholder="Bijv. Albert Heijn, Jumbo, Lidl" />
        </div>
        <div className="form-row">
          <div className="field">
            <label htmlFor="quiet-hours-start">Stilte vanaf</label>
            <input id="quiet-hours-start" name="quiet_hours_start" type="time" defaultValue={preferences.quiet_hours_start ?? ""} />
          </div>
          <div className="field">
            <label htmlFor="quiet-hours-end">Stilte tot</label>
            <input id="quiet-hours-end" name="quiet_hours_end" type="time" defaultValue={preferences.quiet_hours_end ?? ""} />
          </div>
        </div>
        <button className="button primary">Voorkeuren opslaan</button>
      </form>
    </div>
  );
}

function SecurityPanel({ sessions }: { sessions: Array<{ id: string; created_at: string; last_seen_at: string; expires_at: string; is_current: boolean }> }) {
  const otherSessions = sessions.filter((session) => !session.is_current).length;
  const currentSession = sessions.find((session) => session.is_current);

  return (
    <div className="card security-control">
      <div className="section-head">
        <div>
          <h2>Beveiliging</h2>
          <p className="muted">Wachtwoord en actieve lokale sessies.</p>
        </div>
        <span className={otherSessions > 0 ? "status accent" : "status"}>{sessions.length} actief</span>
      </div>
      <div className="security-session-summary">
        <div className="settings-metric">
          <KeyRound size={17} />
          <div>
            <strong>{currentSession ? shortDate(currentSession.expires_at) : "Onbekend"}</strong>
            <span>Huidige sessie verloopt</span>
          </div>
        </div>
        <div className="settings-metric">
          <LogOut size={17} />
          <div>
            <strong>{otherSessions}</strong>
            <span>Andere actieve sessies</span>
          </div>
        </div>
      </div>
      <form className="form" action={changePassword}>
        <div className="field">
          <label htmlFor="current-password">Huidig wachtwoord</label>
          <PasswordInput id="current-password" name="current_password" required autoComplete="current-password" />
        </div>
        <div className="field">
          <label htmlFor="next-password">Nieuw wachtwoord</label>
          <PasswordInput id="next-password" name="next_password" minLength={8} required autoComplete="new-password" />
        </div>
        <button className="button">Wachtwoord wijzigen</button>
      </form>
      <div className="security-session-list">
        <div className="section-head">
          <div>
            <strong>Actieve sessies</strong>
            <p className="muted">Sessies worden server-side opgeslagen en verlopen automatisch.</p>
          </div>
          {otherSessions > 0 && (
            <form action={revokeOtherSessions}>
              <button className="button danger">Andere sessies uitloggen</button>
            </form>
          )}
        </div>
        <ul className="list">
          {sessions.length === 0 && <li className="empty-state">Geen actieve sessies gevonden.</li>}
          {sessions.map((session) => (
            <li className="list-row" key={session.id}>
              <div className="row-main">
                <div className="row-title">{session.is_current ? "Huidige sessie" : "Andere sessie"}</div>
                <div className="row-meta">Actief: {shortDate(session.last_seen_at)} · Verloopt: {shortDate(session.expires_at)}</div>
              </div>
              <span className={session.is_current ? "status" : "status accent"}>{session.is_current ? "Dit apparaat" : "Actief"}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function NotificationsPanel({ data, currentUserId }: { data: Awaited<ReturnType<typeof getLocalAppData>>; currentUserId?: string }) {
  const member = data.members.find((item) => item.user_id === currentUserId);
  const profile = member?.profile;
  const today = dateKey(new Date()) ?? new Date().toISOString().slice(0, 10);
  const tomorrow = addDays(today, 1);
  const dueTasks = data.tasks
    .filter((task) => {
      const dueDate = dateKey(task.due_date);
      return !task.parent_task_id && task.status === "open" && dueDate && dueDate <= tomorrow;
    })
    .slice(0, 4);
  const events = data.calendarEvents
    .filter((event) => {
      const startsAt = dateKey(event.starts_at);
      return startsAt && startsAt >= today && startsAt <= tomorrow;
    })
    .sort((a, b) => dateSortValue(a.starts_at) - dateSortValue(b.starts_at))
    .slice(0, 4);
  const maintenance = data.maintenanceItems
    .filter((item) => {
      const dueDate = dateKey(item.due_date);
      return item.status === "open" && dueDate && dueDate <= tomorrow;
    })
    .slice(0, 3);
  const digestItems = [
    ...dueTasks.map((task) => ({ id: `task-${task.id}`, title: task.title, detail: `${memberName(task.assignee_id, data.members)} · ${shortDate(task.due_date)}`, href: "/taken?filter=vandaag" })),
    ...events.map((event) => ({ id: `event-${event.id}`, title: event.title, detail: shortDate(event.starts_at), href: "/agenda" })),
    ...maintenance.map((item) => ({ id: `maintenance-${item.id}`, title: item.title, detail: shortDate(item.due_date), href: "/onderhoud" })),
  ].slice(0, 6);

  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Mijn meldingen</h2>
          <p className="muted">Persoonlijke voorkeuren en een voorbeeld van je dagoverzicht.</p>
        </div>
        <span className="summary-icon">
          <Bell size={18} />
        </span>
      </div>
      <div className="settings-metrics">
        <div className="settings-metric">
          <Mail size={17} />
          <div>
            <strong>{profile?.notification_email === false ? "E-mail uit" : "E-mail aan"}</strong>
            <span>{profile?.email ?? "Geen e-mailadres"}</span>
          </div>
        </div>
        <div className="settings-metric">
          <Clock size={17} />
          <div>
            <strong>{profile?.digest_time ? profile.digest_time : "Geen dagoverzicht"}</strong>
            <span>Voorkeurstijd</span>
          </div>
        </div>
      </div>
      <ul className="list">
        {digestItems.length === 0 && <li className="empty-state">Geen urgente items voor vandaag of morgen.</li>}
        {digestItems.map((item) => (
          <li className="list-row" key={item.id}>
            <div className="row-main">
              <div className="row-title">{item.title}</div>
              <div className="row-meta">{item.detail}</div>
            </div>
            <Link className="status" href={item.href}>Open</Link>
          </li>
        ))}
      </ul>
      <Link className="button" href="/vandaag">Vandaag openen</Link>
    </div>
  );
}

function InvitesPanel({
  invites,
  origin,
  localMode,
  canCreate,
}: {
  invites: Array<{ id: string; code: string; expires_at?: string; created_at?: string }>;
  origin: string;
  localMode: boolean;
  canCreate: boolean;
}) {
  return (
    <div className="card invite-control">
      <div className="section-head">
        <div>
          <h2>Uitnodigingen</h2>
          <p className="muted">Deel een tijdelijke link of code met gezinsleden. Nieuwe leden starten als lid.</p>
        </div>
        <span className={invites.length > 0 ? "status accent" : "status"}>{invites.length} open</span>
      </div>
      <div className="invite-help-grid">
        <InviteHelp icon={<Link2 size={17} />} title="Deel de link" detail="De link opent direct de acceptatiepagina." />
        <InviteHelp icon={<KeyRound size={17} />} title="Of deel de code" detail="De code kan op de loginpagina worden ingevuld." />
        <InviteHelp icon={<ShieldCheck size={17} />} title="Tijdelijk" detail="Open codes verlopen automatisch na 14 dagen." />
      </div>
      {canCreate ? (
        <form action={createInvite} className="invite-create-row">
          <button className="button primary">Nieuwe invite-code</button>
        </form>
      ) : (
        <div className="empty-state">Alleen eigenaren en beheerders kunnen uitnodigingen maken.</div>
      )}
      <ul className="list invite-list">
        {invites.length === 0 && <li className="empty-state">Geen open uitnodigingen.</li>}
        {invites.map((invite) => {
          const inviteUrl = `${origin}/invite/${invite.code}`;
          return (
            <li className="list-row invite-row" key={invite.id}>
              <div className="row-main">
                <div className="invite-code-row">
                  <span className="invite-code">{invite.code}</span>
                  {invite.expires_at && <span className="status">Verloopt {new Date(invite.expires_at).toLocaleDateString("nl-NL")}</span>}
                </div>
                <div className="invite-link-box">
                  <Copy size={15} />
                  <span>{inviteUrl}</span>
                </div>
                <div className="row-meta">Geef deze link aan een gezinslid, of laat de code invullen op de loginpagina.</div>
              </div>
              <div className="invite-actions">
                <Link className="button" href={`/invite/${invite.code}`}>Open</Link>
                {localMode && (
                  <form action={revokeInvite}>
                    <input type="hidden" name="id" value={invite.id} />
                    <button className="button danger">Intrekken</button>
                  </form>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function InviteHelp({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return (
    <div className="invite-help">
      <span>{icon}</span>
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function SettingsStatus({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="settings-status">
      <span className="settings-status-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function Avatar({ color, name }: { color?: string | null; name: string }) {
  return (
    <span className={`avatar-dot avatar-${color || "groen"}`} aria-hidden="true">
      <UserRound size={18} />
      <span>{initials(name)}</span>
    </span>
  );
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
}

function roleLabel(role: string) {
  if (role === "owner") return "Eigenaar";
  if (role === "admin") return "Beheerder";
  return "Lid";
}

function dashboardLabel(value: string) {
  if (value === "compact") return "Compact";
  if (value === "uitgebreid") return "Uitgebreid";
  return "Vandaag";
}

function addDays(dateValue: string, days: number) {
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

async function requestOrigin() {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const proto = requestHeaders.get("x-forwarded-proto") ?? (host.includes("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}
