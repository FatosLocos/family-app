import Link from "next/link";
import { AlertTriangle, Bell, CalendarDays, CheckSquare, ShoppingBasket, Utensils } from "lucide-react";
import { dateKey } from "@/lib/date-keys";
import { shortDate } from "@/lib/format";
import { buildNotifications } from "@/lib/notifications";
import type { AppData } from "@/lib/types";

export function FamilyCommandCenter({ data, now }: { data: AppData; now: string }) {
  const today = now.slice(0, 10);
  const nowTime = new Date(now).getTime();
  const dueTasks = data.tasks.filter((task) => task.status === "open" && !task.parent_task_id && dateKey(task.due_date) !== null && dateKey(task.due_date)! <= today);
  const openShopping = data.shoppingItems.filter((item) => !item.checked);
  const nextEvent = data.calendarEvents
    .filter((event) => new Date(event.starts_at).getTime() >= nowTime)
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0];
  const nextMeal = data.mealPlans
    .filter((meal) => dateKey(meal.planned_date as string | Date)! >= today)
    .sort((a, b) => dateKey(a.planned_date as string | Date)!.localeCompare(dateKey(b.planned_date as string | Date)!))[0];
  const notifications = buildNotifications(data, now);
  const urgent = notifications.filter((item) => item.tone === "urgent").length;

  const commands = [
    {
      title: dueTasks.length > 0 ? `${dueTasks.length} taak${dueTasks.length === 1 ? "" : "en"} nu` : "Taken op orde",
      detail: dueTasks[0]?.title ?? "Bekijk open acties of voeg iets toe.",
      href: "/taken?filter=vandaag",
      icon: <CheckSquare size={18} />,
      tone: dueTasks.length > 0 ? "attention" : "calm",
    },
    {
      title: openShopping.length > 0 ? `${openShopping.length} boodschap${openShopping.length === 1 ? "" : "pen"}` : "Lijst is leeg",
      detail: openShopping[0]?.name ?? "Zet terugkerende producten op de lijst.",
      href: "/boodschappen",
      icon: <ShoppingBasket size={18} />,
      tone: openShopping.length > 0 ? "neutral" : "calm",
    },
    {
      title: nextEvent ? "Volgende afspraak" : "Agenda vrij",
      detail: nextEvent ? `${nextEvent.title} · ${shortDate(nextEvent.starts_at)}` : "Plan gezinsafspraken of sync Outlook.",
      href: "/agenda",
      icon: <CalendarDays size={18} />,
      tone: nextEvent ? "neutral" : "calm",
    },
    {
      title: nextMeal ? "Eten gepland" : "Nog geen maaltijd",
      detail: nextMeal ? `${nextMeal.title} · ${shortDate(nextMeal.planned_date)}` : "Plan een maaltijd en zet ingredienten op de lijst.",
      href: "/boodschappen?tab=maaltijden",
      icon: <Utensils size={18} />,
      tone: nextMeal ? "neutral" : "attention",
    },
    {
      title: urgent > 0 ? `${urgent} urgent` : "Meldingen rustig",
      detail: notifications[0]?.title ?? "Geen directe signalen.",
      href: "/meldingen",
      icon: <Bell size={18} />,
      tone: urgent > 0 ? "urgent" : "calm",
    },
    {
      title: "Noodkaart",
      detail: "Contacten, huisinfo en documenten direct bij de hand.",
      href: "/noodkaart",
      icon: <AlertTriangle size={18} />,
      tone: "neutral",
    },
  ] as const;

  return (
    <section className="command-center" aria-label="Dagstart">
      <div className="section-head">
        <div>
          <h2>Dagstart</h2>
          <p className="muted">De belangrijkste gezinsacties in vaste volgorde.</p>
        </div>
        <Link className="status" href="/activiteit">
          Activiteit
        </Link>
      </div>
      <div className="command-grid">
        {commands.map((command) => (
          <Link className={`command-card ${command.tone}`} href={command.href} key={command.href}>
            <span className="summary-icon">{command.icon}</span>
            <span>
              <strong>{command.title}</strong>
              <small>{command.detail}</small>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
