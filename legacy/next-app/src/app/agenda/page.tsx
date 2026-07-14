import { redirect } from "next/navigation";
import Link from "next/link";
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, ExternalLink, MapPin, UsersRound } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { BirthdayForm, CalendarForm, IcsCalendarFileImportForm, IcsCalendarSubscriptionForm } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { ModuleLayout } from "@/components/module-layout";
import { BirthdayCalendarCard, CalendarIntegrationsPanel, CalendarList } from "@/components/module-lists";
import { getAppData, getUser } from "@/lib/local-data";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { dateKey, dateSortValue } from "@/lib/date-keys";
import { demoData } from "@/lib/demo-data";
import { memberName } from "@/lib/format";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

type CalendarSearchParams = {
  outlook_status?: string;
  outlook_error?: string;
  outlook_filter?: string;
  outlook_calendar?: string | string[];
  agenda_view?: string;
  agenda_date?: string;
};

type AgendaView = "dag" | "week" | "maand";

export default async function CalendarPage({ searchParams }: { searchParams?: Promise<CalendarSearchParams> }) {
  if (hasLocalDatabaseEnv()) {
    const params = await searchParams;
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <CalendarContent data={await getLocalAppData()} searchParams={params} outlookStatus={params?.outlook_status} outlookError={params?.outlook_error} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="agenda" />;
  const params = await searchParams;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <CalendarContent data={data} searchParams={params} outlookStatus={params?.outlook_status} outlookError={params?.outlook_error} />;
}

function CalendarContent({
  data,
  searchParams,
  demo = false,
  outlookStatus,
  outlookError,
}: {
  data: typeof demoData;
  searchParams?: CalendarSearchParams;
  demo?: boolean;
  outlookStatus?: string;
  outlookError?: string;
}) {
  const outlookCalendars = getOutlookCalendars(data);
  const requestedOutlookCalendarIds = queryValues(searchParams?.outlook_calendar);
  const selectedOutlookCalendarIds = new Set(
    searchParams?.outlook_filter === "1"
      ? outlookCalendars.filter((calendar) => requestedOutlookCalendarIds.includes(calendar.id)).map((calendar) => calendar.id)
      : outlookCalendars.map((calendar) => calendar.id),
  );
  const visibleData = {
    ...data,
    calendarEvents: data.calendarEvents.filter(
      (event) => event.source_provider !== "outlook" || !event.external_calendar_id || selectedOutlookCalendarIds.has(event.external_calendar_id),
    ),
  };
  const today = dateKey(new Date()) ?? new Date().toISOString().slice(0, 10);
  const upcoming = visibleData.calendarEvents.filter((event) => dateKey(event.starts_at)! >= today);
  const todayEvents = upcoming.filter((event) => dateKey(event.starts_at) === today);
  const view = agendaView(searchParams?.agenda_view);
  const selectedDate = agendaDate(searchParams?.agenda_date, today);
  return (
    <AppShell demo={demo}>
      <ModuleLayout
        asideLabel="Agenda-acties"
        aside={demo ? <DemoPanel /> : <><CalendarIntegrationsPanel data={data} /><ModuleSubmenu title="Afspraak toevoegen" detail="Gezinsafspraak met deelnemers en tijd"><CalendarForm members={data.members} /></ModuleSubmenu><ModuleSubmenu title="Verjaardag toevoegen" detail="Jaarlijks terugkerende verjaardag in de gezinskalender"><BirthdayForm members={data.members} /></ModuleSubmenu><ModuleSubmenu title="ICS agenda toevoegen" detail="Gedeelde of openbare agenda via een abonnement koppelen"><IcsCalendarSubscriptionForm /></ModuleSubmenu><ModuleSubmenu title="ICS-bestand importeren" detail="Een lokaal .ics-bestand eenmalig inlezen"><IcsCalendarFileImportForm /></ModuleSubmenu></>}
      >
        <div className="grid">
          <CompactModuleHeader
            eyebrow="Planning"
            title="Agenda"
            stats={[
              { label: "vandaag", value: todayEvents.length },
              { label: "aankomend", value: upcoming.length },
              { label: "koppelingen", value: data.calendarIntegrations.length + (data.icsCalendarSubscriptions?.length ?? 0) + (data.icsCalendarFileImports?.length ?? 0) },
            ]}
          >
            Gezinsplanning, agenda-koppelingen en drukke dagen in een overzicht.
          </CompactModuleHeader>
          {outlookStatus && <p className="status">Outlook agenda gekoppeld.</p>}
          {outlookError && <p className="status">Outlook fout: {outlookError}</p>}
          <OutlookCalendarFilter calendars={outlookCalendars} selectedIds={selectedOutlookCalendarIds} />
          <AgendaCalendarView data={visibleData} view={view} selectedDate={selectedDate} searchParams={searchParams} />
          <BirthdayCalendarCard data={visibleData} readOnly={demo} />
          <section className="agenda-all card">
            <div className="section-head">
              <div>
                <h2>Alle afspraken</h2>
                <p className="muted">Alles wat in de gedeelde agenda staat.</p>
              </div>
              <span className="status">{visibleData.calendarEvents.length}</span>
            </div>
            <CalendarList data={visibleData} readOnly={demo} />
          </section>
        </div>
      </ModuleLayout>
    </AppShell>
  );
}

function OutlookCalendarFilter({
  calendars,
  selectedIds,
}: {
  calendars: Array<{ id: string; name: string }>;
  selectedIds: Set<string>;
}) {
  if (calendars.length === 0) return null;

  return (
    <details className="agenda-calendar-filter" open={selectedIds.size !== calendars.length}>
      <summary>
        <span>Outlook agenda&apos;s</span>
        <strong>{selectedIds.size}/{calendars.length}</strong>
      </summary>
      <form method="get" className="agenda-calendar-filter-form">
        <input type="hidden" name="outlook_filter" value="1" />
        <fieldset>
          <legend>Toon in agenda</legend>
          <div className="agenda-calendar-filter-options">
            {calendars.map((calendar) => (
              <label key={calendar.id}>
                <input type="checkbox" name="outlook_calendar" value={calendar.id} defaultChecked={selectedIds.has(calendar.id)} />
                <span>{calendar.name}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="agenda-calendar-filter-actions">
          <button className="button">Toepassen</button>
          <Link className="button ghost" href="/agenda">Alles tonen</Link>
        </div>
      </form>
    </details>
  );
}

function getOutlookCalendars(data: AppData) {
  const calendars = new Map<string, string>();
  for (const event of data.calendarEvents) {
    if (event.source_provider !== "outlook" || !event.external_calendar_id) continue;
    calendars.set(event.external_calendar_id, event.external_calendar_name ?? "Outlook agenda");
  }
  return [...calendars.entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((left, right) => left.name.localeCompare(right.name, "nl-NL"));
}

function queryValues(value: string | string[] | undefined) {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

function AgendaCalendarView({
  data,
  view,
  selectedDate,
  searchParams,
}: {
  data: AppData;
  view: AgendaView;
  selectedDate: string;
  searchParams?: CalendarSearchParams;
}) {
  const today = dateKey(new Date()) ?? new Date().toISOString().slice(0, 10);
  const range = agendaRange(view, selectedDate);
  const eventsByDate = new Map<string, AppData["calendarEvents"]>();

  for (const event of data.calendarEvents) {
    const key = dateKey(event.starts_at);
    if (!key || key < range.start || key > range.end) continue;
    const events = eventsByDate.get(key) ?? [];
    events.push(event);
    eventsByDate.set(key, events);
  }
  for (const events of eventsByDate.values()) events.sort((left, right) => eventMomentValue(left.starts_at) - eventMomentValue(right.starts_at));

  const previousDate = shiftAgendaDate(view, selectedDate, -1);
  const nextDate = shiftAgendaDate(view, selectedDate, 1);
  const navigation = (date: string, nextView = view) => agendaHref({ view: nextView, date, searchParams });

  return (
    <section className={`agenda-calendar agenda-calendar-${view} card`}>
      <div className="agenda-calendar-toolbar">
        <div className="agenda-view-switch" aria-label="Agendaweergave">
          {(["dag", "week", "maand"] as const).map((option) => (
            <Link
              aria-current={view === option ? "page" : undefined}
              className={view === option ? "active" : undefined}
              href={navigation(selectedDate, option)}
              key={option}
            >
              {option}
            </Link>
          ))}
        </div>
        <div className="agenda-date-nav">
          <Link aria-label="Vorige periode" className="icon-button" href={navigation(previousDate)} title="Vorige periode"><ChevronLeft size={17} /></Link>
          <Link className="agenda-date-title" href={navigation(today)}>{agendaRangeLabel(view, range)}</Link>
          <Link aria-label="Volgende periode" className="icon-button" href={navigation(nextDate)} title="Volgende periode"><ChevronRight size={17} /></Link>
        </div>
        <Link className="agenda-today-link" href={navigation(today)}>
          <CalendarDays size={15} /> Vandaag
        </Link>
      </div>
      {view === "dag" && <AgendaDayView date={selectedDate} events={eventsByDate.get(selectedDate) ?? []} today={today} members={data.members} />}
      {view === "week" && <AgendaWeekView range={range} eventsByDate={eventsByDate} today={today} members={data.members} />}
      {view === "maand" && <AgendaMonthView range={range} eventsByDate={eventsByDate} today={today} members={data.members} />}
    </section>
  );
}

function AgendaDayView({ date, events, today, members }: { date: string; events: AppData["calendarEvents"]; today: string; members: AppData["members"] }) {
  return (
    <div className="agenda-day-view">
      <div className="agenda-calendar-day-heading">
        <span>{date === today ? "Vandaag" : new Intl.DateTimeFormat("nl-NL", { weekday: "long" }).format(calendarDate(date))}</span>
        <strong>{new Intl.DateTimeFormat("nl-NL", { day: "numeric", month: "long" }).format(calendarDate(date))}</strong>
      </div>
      <AgendaEventList events={events} members={members} emptyLabel="Geen afspraken op deze dag." />
    </div>
  );
}

function AgendaWeekView({ range, eventsByDate, today, members }: { range: AgendaRange; eventsByDate: Map<string, AppData["calendarEvents"]>; today: string; members: AppData["members"] }) {
  return (
    <div className="agenda-week-view" aria-label="Weekagenda">
      {range.days.map((date) => {
        const events = eventsByDate.get(date) ?? [];
        return (
          <article className={`agenda-week-column${date === today ? " today" : ""}`} key={date}>
            <header>
              <span>{new Intl.DateTimeFormat("nl-NL", { weekday: "short" }).format(calendarDate(date))}</span>
              <strong>{new Intl.DateTimeFormat("nl-NL", { day: "numeric", month: "short" }).format(calendarDate(date))}</strong>
            </header>
            <AgendaEventList events={events} members={members} emptyLabel="" compact />
          </article>
        );
      })}
    </div>
  );
}

function AgendaMonthView({ range, eventsByDate, today, members }: { range: AgendaRange; eventsByDate: Map<string, AppData["calendarEvents"]>; today: string; members: AppData["members"] }) {
  return (
    <div className="agenda-month-view" aria-label="Maandagenda">
      {["ma", "di", "wo", "do", "vr", "za", "zo"].map((day) => <span className="agenda-month-weekday" key={day}>{day}</span>)}
      {range.days.map((date) => {
        const events = eventsByDate.get(date) ?? [];
        const inCurrentMonth = date.slice(0, 7) === range.currentMonth;
        return (
          <article className={`agenda-month-day${date === today ? " today" : ""}${inCurrentMonth ? "" : " outside"}`} key={date}>
            <strong>{new Intl.DateTimeFormat("nl-NL", { day: "numeric" }).format(calendarDate(date))}</strong>
            <AgendaEventList events={events} members={members} emptyLabel="" compact maxEvents={3} />
          </article>
        );
      })}
    </div>
  );
}

function AgendaEventList({
  events,
  members,
  emptyLabel,
  compact = false,
  maxEvents,
}: {
  events: AppData["calendarEvents"];
  members: AppData["members"];
  emptyLabel: string;
  compact?: boolean;
  maxEvents?: number;
}) {
  const visibleEvents = maxEvents ? events.slice(0, maxEvents) : events;
  return (
    <ul className={`agenda-event-list${compact ? " compact" : ""}`}>
      {visibleEvents.map((event) => {
        const popoverId = `agenda-event-${event.id}`;
        const tooltip = `${event.title} · ${formatEventMoment(event)} · ${eventSourceLabel(event)}`;
        return (
        <li className={event.is_all_day ? "all-day" : ""} key={event.id}>
          <button className="agenda-event-trigger" type="button" popoverTarget={popoverId} title={tooltip} data-tooltip={tooltip}>
            <time>{event.is_all_day ? "Hele dag" : timeLabel(event.starts_at)}</time>
            <span>{event.title}</span>
          </button>
          <AgendaEventDetailsPopover event={event} members={members} popoverId={popoverId} />
        </li>
        );
      })}
      {maxEvents && events.length > maxEvents && <li className="agenda-event-more">+{events.length - maxEvents} meer</li>}
      {events.length === 0 && emptyLabel && <li className="agenda-event-empty">{emptyLabel}</li>}
    </ul>
  );
}

function AgendaEventDetailsPopover({
  event,
  members,
  popoverId,
}: {
  event: AppData["calendarEvents"][number];
  members: AppData["members"];
  popoverId: string;
}) {
  const participants = event.participant_ids.map((id) => memberName(id, members)).filter(Boolean);
  return (
    <div className="app-popover agenda-event-popover" id={popoverId} popover="auto">
      <div className="agenda-event-popover-head">
        <div>
          <span className="eyebrow">Afspraak</span>
          <h2>{event.title}</h2>
          <p className="muted">{eventSourceLabel(event)}</p>
        </div>
        <button className="icon-button" type="button" popoverTarget={popoverId} popoverTargetAction="hide" aria-label="Afspraak sluiten" title="Sluiten">×</button>
      </div>
      <dl className="agenda-event-details">
        <div>
          <dt><Clock3 size={16} /> Wanneer</dt>
          <dd>{formatEventMoment(event)}</dd>
        </div>
        {event.location && <div>
          <dt><MapPin size={16} /> Locatie</dt>
          <dd>{event.location}</dd>
        </div>}
        {participants.length > 0 && <div>
          <dt><UsersRound size={16} /> Deelnemers</dt>
          <dd>{participants.join(", ")}</dd>
        </div>}
        {event.organizer_name && <div>
          <dt>Organisator</dt>
          <dd>{event.organizer_name}</dd>
        </div>}
      </dl>
      {event.web_link && <a className="agenda-event-external-link" href={event.web_link} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open in Outlook</a>}
    </div>
  );
}

type AgendaRange = {
  start: string;
  end: string;
  days: string[];
  currentMonth: string;
};

function agendaView(value: string | undefined): AgendaView {
  return value === "dag" || value === "maand" ? value : "week";
}

function agendaDate(value: string | undefined, fallback: string) {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(new Date(`${value}T12:00:00.000Z`).getTime()) ? value : fallback;
}

function agendaRange(view: AgendaView, date: string): AgendaRange {
  if (view === "dag") return { start: date, end: date, days: [date], currentMonth: date.slice(0, 7) };
  if (view === "week") {
    const start = startOfWeek(date);
    const days = Array.from({ length: 7 }, (_, index) => addDays(start, index));
    return { start, end: days[6], days, currentMonth: date.slice(0, 7) };
  }

  const monthStart = `${date.slice(0, 7)}-01`;
  const start = startOfWeek(monthStart);
  const days = Array.from({ length: 42 }, (_, index) => addDays(start, index));
  return { start, end: days[days.length - 1], days, currentMonth: date.slice(0, 7) };
}

function agendaRangeLabel(view: AgendaView, range: AgendaRange) {
  if (view === "dag") return new Intl.DateTimeFormat("nl-NL", { weekday: "long", day: "numeric", month: "long" }).format(calendarDate(range.start));
  if (view === "maand") return new Intl.DateTimeFormat("nl-NL", { month: "long", year: "numeric" }).format(calendarDate(`${range.currentMonth}-01`));
  const sameMonth = range.start.slice(0, 7) === range.end.slice(0, 7);
  const startFormat = new Intl.DateTimeFormat("nl-NL", sameMonth ? { day: "numeric" } : { day: "numeric", month: "short" });
  const endFormat = new Intl.DateTimeFormat("nl-NL", { day: "numeric", month: "short" });
  return `${startFormat.format(calendarDate(range.start))} - ${endFormat.format(calendarDate(range.end))}`;
}

function agendaHref({ view, date, searchParams }: { view: AgendaView; date: string; searchParams?: CalendarSearchParams }) {
  const params = new URLSearchParams({ agenda_view: view, agenda_date: date });
  if (searchParams?.outlook_filter === "1") {
    params.set("outlook_filter", "1");
    for (const calendarId of queryValues(searchParams.outlook_calendar)) params.append("outlook_calendar", calendarId);
  }
  return `/agenda?${params.toString()}`;
}

function shiftAgendaDate(view: AgendaView, date: string, direction: -1 | 1) {
  if (view === "dag") return addDays(date, direction);
  if (view === "week") return addDays(date, direction * 7);
  const value = calendarDate(`${date.slice(0, 7)}-01`);
  value.setUTCMonth(value.getUTCMonth() + direction);
  return value.toISOString().slice(0, 10);
}

function startOfWeek(date: string) {
  const value = calendarDate(date);
  const weekday = value.getUTCDay();
  return addDays(date, weekday === 0 ? -6 : 1 - weekday);
}

function calendarDate(date: string) {
  return new Date(`${date}T12:00:00.000Z`);
}

function eventMomentValue(value: string) {
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? dateSortValue(value) : timestamp;
}

function addDays(date: string, days: number) {
  const value = new Date(`${date}T12:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function timeLabel(value: string) {
  return new Intl.DateTimeFormat("nl-NL", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function formatEventMoment(event: AppData["calendarEvents"][number]) {
  const date = new Intl.DateTimeFormat("nl-NL", { day: "numeric", month: "short", year: "numeric" }).format(new Date(event.starts_at));
  if (event.is_all_day) return `${date} · hele dag`;
  const end = event.ends_at && timeLabel(event.ends_at) !== timeLabel(event.starts_at) ? ` - ${timeLabel(event.ends_at)}` : "";
  return `${date} · ${timeLabel(event.starts_at)}${end}`;
}

function eventSourceLabel(event: AppData["calendarEvents"][number]) {
  if (!event.source_provider) return "Gezin";
  return event.external_calendar_name ?? (event.source_provider === "ics" ? "ICS agenda" : "Outlook");
}

function DemoPanel() {
  return (
    <div className="card">
      <h2>Demo-modus</h2>
      <p className="muted">Configureer PostgreSQL om gezinsafspraken echt toe te voegen.</p>
    </div>
  );
}
