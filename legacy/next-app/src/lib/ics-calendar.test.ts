import { describe, expect, it } from "vitest";
import { parseIcsEvents } from "@/lib/ics-calendar";

describe("parseIcsEvents", () => {
  it("leest tijdgebonden en hele-dag afspraken uit een ICS-feed", () => {
    const events = parseIcsEvents(`BEGIN:VCALENDAR
BEGIN:VEVENT
UID:school-1
SUMMARY:Ouderavond\\, groep 6
DTSTART:20260714T183000Z
DTEND:20260714T193000Z
LOCATION:School
URL:https://example.test/event
END:VEVENT
BEGIN:VEVENT
UID:vakantie-1
SUMMARY:Zomervakantie
DTSTART;VALUE=DATE:20260720
DTEND;VALUE=DATE:20260721
END:VEVENT
END:VCALENDAR`);

    expect(events).toEqual([
      expect.objectContaining({ id: "school-1", title: "Ouderavond, groep 6", startsAt: "2026-07-14T18:30:00.000Z", isAllDay: false }),
      expect.objectContaining({ id: "vakantie-1", title: "Zomervakantie", startsAt: "2026-07-20T00:00:00.000Z", isAllDay: true }),
    ]);
  });

  it("slaat geannuleerde afspraken over", () => {
    const events = parseIcsEvents(`BEGIN:VEVENT
UID:geannuleerd
SUMMARY:Vervallen
STATUS:CANCELLED
DTSTART:20260714T183000Z
END:VEVENT`);
    expect(events).toEqual([]);
  });
});
