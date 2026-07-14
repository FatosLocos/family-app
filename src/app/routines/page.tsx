import Link from "next/link";
import { redirect } from "next/navigation";
import { CheckSquare, ShoppingBasket, Wrench } from "lucide-react";
import { addRecurringProductToShopping, completeMaintenanceItem, toggleTask } from "@/app/actions";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { dateKey } from "@/lib/date-keys";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { memberName, shortDate } from "@/lib/format";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { buildRoutineReadiness, maintenanceLabel, recurrenceLabel } from "@/lib/routine-readiness";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function RoutinesPage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <RoutinesContent data={await getLocalAppData()} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <RoutinesContent data={data} />;
}

function RoutinesContent({ data }: { data: AppData }) {
  const today = dateKey(new Date()) ?? new Date().toISOString().slice(0, 10);
  const readiness = buildRoutineReadiness(data, today);
  const { activeRoutineTasks, recurringProducts, activeRecurringMaintenance, dueRoutineTasks, dueProducts, dueMaintenance } = readiness;
  const upcomingItems = [
    ...dueRoutineTasks.map((task) => ({
      id: `task-${task.id}`,
      type: "Taak",
      title: task.title,
      detail: `${recurrenceLabel(task.recurrence)} · ${memberName(task.assignee_id, data.members)} · ${shortDate(task.due_date)}`,
      href: "/taken?filter=vandaag",
      tone: dateKey(task.due_date) && dateKey(task.due_date)! < today ? "urgent" : "attention",
    })),
    ...dueProducts.map((product) => ({
      id: `product-${product.id}`,
      type: "Boodschap",
      title: product.name,
      detail: `${recurrenceLabel(product.recurrence)} · ${product.default_quantity ?? "Geen hoeveelheid"}`,
      href: "/boodschappen",
      tone: "attention",
    })),
    ...dueMaintenance.map((item) => ({
      id: `maintenance-${item.id}`,
      type: "Onderhoud",
      title: item.title,
      detail: `${maintenanceLabel(item.frequency)} · ${shortDate(item.due_date)}`,
      href: "/onderhoud",
      tone: dateKey(item.due_date) && dateKey(item.due_date)! < today ? "urgent" : "attention",
    })),
  ].slice(0, 6);

  return (
    <AppShell>
      <CompactModuleHeader
        eyebrow="Dagelijks"
        title="Routines"
        stats={[
          { label: "actief", value: readiness.total },
          { label: "taken", value: activeRoutineTasks.length },
          { label: "boodschappen", value: recurringProducts.length },
          { label: "onderhoud", value: activeRecurringMaintenance.length },
          { label: "deze week", value: readiness.dueThisWeek },
          { label: "mist planning", value: readiness.withoutDate },
        ]}
      >
        Alle terugkerende gezinszaken op een plek: taken, producten en huisonderhoud.
      </CompactModuleHeader>

      <section className="routine-week-strip card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Deze week</span>
            <h2>Routines opvolgen</h2>
            <p className="muted">Alle vaste zaken die nu of binnenkort aandacht vragen.</p>
          </div>
          <span className={upcomingItems.some((item) => item.tone === "urgent") ? "status accent" : "status"}>
            {upcomingItems.length} acties
          </span>
        </div>
        <div className="routine-week-grid">
          {upcomingItems.length === 0 ? (
            <div className="empty-state">Geen routine-acties voor deze week. Open Week voor de rest van de planning.</div>
          ) : (
            upcomingItems.map((item) => (
              <Link className={`routine-week-card ${item.tone}`} href={item.href} key={item.id}>
                <span>{item.type}</span>
                <strong>{item.title}</strong>
                <small>{item.detail}</small>
              </Link>
            ))
          )}
        </div>
      </section>

      <section className="grid three-col section-stack">
        <div className="card module-card">
          <RoutineHead icon={<CheckSquare size={18} />} title="Taken" count={activeRoutineTasks.length} href="/taken" />
          <ul className="list">
            {activeRoutineTasks.length === 0 && <li className="empty-state">Geen open terugkerende taken. Maak een taak met herhaling aan of rond de volgende instantie af.</li>}
            {activeRoutineTasks.map((task) => (
              <li className="list-row routine-row" key={task.id}>
                <div className="row-main">
                  <div className="row-title">{task.title}</div>
                  <div className="row-meta">{recurrenceLabel(task.recurrence)} · {memberName(task.assignee_id, data.members)} · {shortDate(task.due_date)}</div>
                  {task.description && <div className="row-description">{task.description}</div>}
                </div>
                {task.status === "open" ? (
                  <form action={toggleTask}>
                    <input type="hidden" name="id" value={task.id} />
                    <input type="hidden" name="status" value={task.status} />
                    <button className="button">Afronden</button>
                  </form>
                ) : (
                  <span className="status">Gedaan</span>
                )}
              </li>
            ))}
          </ul>
        </div>

        <div className="card module-card">
          <RoutineHead icon={<ShoppingBasket size={18} />} title="Boodschappen" count={recurringProducts.length} href="/boodschappen" />
          <ul className="list">
            {recurringProducts.length === 0 && <li className="empty-state">Nog geen terugkerende producten. Zet herhaling op wekelijk, tweewekelijks of maandelijks.</li>}
            {recurringProducts.map((product) => (
              <li className="list-row routine-row" key={product.id}>
                <div className="row-main">
                  <div className="row-title">{product.name}</div>
                  <div className="row-meta">{recurrenceLabel(product.recurrence)} · {product.default_quantity ?? "Geen standaardhoeveelheid"}</div>
                  <div className="row-description">{product.purchase_count}x gekocht · laatst {shortDate(product.last_purchased_at)}</div>
                </div>
                <form action={addRecurringProductToShopping}>
                  <input type="hidden" name="product_id" value={product.id} />
                  <button className="button">Op lijst</button>
                </form>
              </li>
            ))}
          </ul>
        </div>

        <div className="card module-card">
          <RoutineHead icon={<Wrench size={18} />} title="Onderhoud" count={activeRecurringMaintenance.length} href="/onderhoud" />
          <ul className="list">
            {activeRecurringMaintenance.length === 0 && <li className="empty-state">Geen open terugkerend onderhoud. Voeg periodieke controles toe of rond de volgende controle af.</li>}
            {activeRecurringMaintenance.map((item) => (
              <li className="list-row routine-row" key={item.id}>
                <div className="row-main">
                  <div className="row-title">{item.title}</div>
                  <div className="row-meta">{maintenanceLabel(item.frequency)} · {shortDate(item.due_date)}</div>
                  <div className="row-description">{[item.area, item.provider, item.notes].filter(Boolean).join(" · ") || "Onderhoud"}</div>
                </div>
                {item.status === "open" ? (
                  <form action={completeMaintenanceItem}>
                    <input type="hidden" name="id" value={item.id} />
                    <button className="button">Afronden</button>
                  </form>
                ) : (
                  <span className="status">Gedaan</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      </section>
    </AppShell>
  );
}

function RoutineHead({ icon, title, count, href }: { icon: React.ReactNode; title: string; count: number; href: string }) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        <p className="muted">{count} routine{count === 1 ? "" : "s"}</p>
      </div>
      <Link className="summary-icon" href={href} title={`${title} openen`}>
        {icon}
      </Link>
    </div>
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

function RoutineMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="routine-metric">
      <span className="routine-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}
