import { getLocalUser } from "@/lib/local-auth";
import { query } from "@/lib/local-db";
import type { IcsCalendarSubscription } from "@/lib/types";

type IcsSubscriptionRecord = IcsCalendarSubscription & { feed_url: string };

export type IcsCalendarEventTarget = Pick<IcsCalendarSubscription, "id" | "household_id" | "user_id" | "display_name">;

type ParsedIcsEvent = {
  id: string;
  title: string;
  startsAt: string;
  endsAt: string | null;
  location: string | null;
  isAllDay: boolean;
  webLink: string | null;
};

export async function getIcsSubscriptionForCurrentUser(id: string) {
  const user = await getLocalUser();
  if (!user) return { error: "Niet ingelogd.", status: 401 as const };
  const result = await query<IcsSubscriptionRecord>(
    `select id, household_id, user_id, display_name, feed_url, status, last_sync_at
     from ics_calendar_subscriptions
     where id = $1 and user_id = $2`,
    [id, user.id],
  );
  const subscription = result.rows[0];
  if (!subscription) return { error: "ICS-abonnement niet gevonden.", status: 404 as const };
  return { subscription };
}

export async function syncIcsCalendar(subscription: IcsSubscriptionRecord) {
  const response = await fetch(subscription.feed_url, {
    headers: { Accept: "text/calendar, text/plain;q=0.9, */*;q=0.1" },
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`ICS-server gaf status ${response.status}.`);
  const body = await response.text();
  if (body.length > 2_000_000) throw new Error("ICS-bestand is te groot.");
  const events = parseIcsEvents(body);

  const result = await upsertIcsCalendarEvents(subscription, events);

  await query("update ics_calendar_subscriptions set status = 'configured', last_sync_at = now(), updated_at = now() where id = $1", [subscription.id]);
  return result;
}

export async function upsertIcsCalendarEvents(target: IcsCalendarEventTarget, events: ParsedIcsEvent[]) {
  for (const event of events) {
    await query(
        `insert into calendar_events
          (household_id, integration_id, external_event_id, external_calendar_id, external_calendar_name, source_provider,
           title, starts_at, ends_at, location, participant_ids, is_all_day, web_link, raw, updated_at)
         values ($1, $2, $3, $4, $5, 'ics', $6, $7, $8, $9, $10::uuid[], $11, $12, $13::jsonb, now())
         on conflict (integration_id, external_event_id) do update set
           title = excluded.title, starts_at = excluded.starts_at, ends_at = excluded.ends_at, location = excluded.location,
           is_all_day = excluded.is_all_day, web_link = excluded.web_link, raw = excluded.raw, updated_at = now()`,
        [target.household_id, target.id, event.id, target.id, target.display_name, event.title, event.startsAt, event.endsAt, event.location, [target.user_id], event.isAllDay, event.webLink, JSON.stringify(event)],
    );
  }
  return { count: events.length };
}

export async function markIcsSyncError(id: string) {
  await query("update ics_calendar_subscriptions set status = 'sync_error', updated_at = now() where id = $1", [id]);
}

export function parseIcsEvents(content: string): ParsedIcsEvent[] {
  const lines = content.replace(/\r\n?/g, "\n").replace(/\n[ \t]/g, "").split("\n");
  const events: ParsedIcsEvent[] = [];
  let fields: Record<string, { value: string; params: string }> | null = null;

  for (const line of lines) {
    if (line === "BEGIN:VEVENT") {
      fields = {};
      continue;
    }
    if (line === "END:VEVENT" && fields) {
      const start = parseIcsDate(fields.DTSTART);
      if (start && fields.STATUS?.value.toUpperCase() !== "CANCELLED") {
        const end = parseIcsDate(fields.DTEND);
        const allDay = fields.DTSTART.value.length === 8;
        events.push({
          id: unescapeIcs(fields.UID?.value || `${fields.SUMMARY?.value || "afspraak"}-${start.iso}`),
          title: unescapeIcs(fields.SUMMARY?.value || "Agenda-afspraak"),
          startsAt: start.iso,
          endsAt: end?.iso ?? defaultEnd(start.iso, allDay),
          location: fields.LOCATION ? unescapeIcs(fields.LOCATION.value) : null,
          isAllDay: allDay,
          webLink: fields.URL ? unescapeIcs(fields.URL.value) : null,
        });
      }
      fields = null;
      continue;
    }
    if (!fields) continue;
    const separator = line.indexOf(":");
    if (separator < 1) continue;
    const key = line.slice(0, separator);
    const name = key.split(";", 1)[0].toUpperCase();
    if (["UID", "SUMMARY", "DTSTART", "DTEND", "LOCATION", "URL", "STATUS"].includes(name)) {
      fields[name] = { value: line.slice(separator + 1), params: key.slice(name.length) };
    }
  }

  return events.slice(0, 1_000);
}

function parseIcsDate(field?: { value: string; params: string }) {
  if (!field) return null;
  const value = field.value.trim();
  if (/^\d{8}$/.test(value)) return { iso: `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}T00:00:00.000Z` };
  const match = value.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z)?$/);
  if (!match) return null;
  const [, year, month, day, hour, minute, second = "00", utc] = match;
  const isoInput = `${year}-${month}-${day}T${hour}:${minute}:${second}${utc ? "Z" : ""}`;
  const timestamp = Date.parse(isoInput);
  return Number.isNaN(timestamp) ? null : { iso: new Date(timestamp).toISOString() };
}

function defaultEnd(start: string, allDay: boolean) {
  return new Date(Date.parse(start) + (allDay ? 86_400_000 : 3_600_000)).toISOString();
}

function unescapeIcs(value: string) {
  return value.replace(/\\n/gi, " ").replace(/\\,/g, ",").replace(/\\;/g, ";").replace(/\\\\/g, "\\").trim();
}
