import { BadgePercent, CalendarDays, Check, CheckSquare, ExternalLink, Gift, Landmark, Mail, MapPin, Phone, Plus, ShoppingBasket, Store, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { OutlookCalendarActions } from "@/components/outlook-calendar-actions";
import { IcsCalendarActions } from "@/components/ics-calendar-actions";
import { RecurringCostGroups } from "@/components/recurring-cost-groups";
import {
  addSubtask,
  addMealIngredientsToShopping,
  completeMaintenanceItem,
  deleteCalendarEvent,
  deleteHouseholdBirthday,
  deleteIcsCalendarSource,
  deleteFinanceBudget,
  deleteFinanceItem,
  deleteHouseholdContact,
  deleteHouseholdDocument,
  deleteHouseholdInfoItem,
  deleteHouseholdNote,
  deleteWishlistItem,
  deleteMaintenanceItem,
  deleteMealPlan,
  deleteShoppingItem,
  deleteTask,
  markFinanceItemPaid,
  setRecurringTransactionRule,
  toggleShoppingItem,
  toggleTask,
  toggleHouseholdNotePin,
  setWishlistItemStatus,
  toggleWishlistItemPublic,
} from "@/app/actions";
import { getShoppingPriceProviderStatus } from "@/lib/env";
import { memberName, money, shortDate } from "@/lib/format";
import { buildRecurringCashflowTrend, buildRecurringCostInsights } from "@/lib/finance-insights";
import { hasKauflandProvider } from "@/lib/kaufland-provider";
import { buildBasketPriceComparison } from "@/lib/shopping-price-comparison";
import type { AppData, PriceObservation } from "@/lib/types";

export function HouseholdDocumentList({ data, limit, readOnly = false }: { data: AppData; limit?: number; readOnly?: boolean }) {
  const documents = limit ? data.householdDocuments.slice(0, limit) : data.householdDocuments;
  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Documenten</h2>
          <p className="muted">Bewaarplekken, referenties en vervaldatums van belangrijke documenten.</p>
        </div>
        <span className="status">{data.householdDocuments.length}</span>
      </div>
      <ul className="list">
        {documents.length === 0 && <li className="empty-state">Nog geen documenten.</li>}
        {documents.map((document) => (
          <li className="list-row" key={document.id}>
            <div className="row-main">
              <div className="row-title">{document.title}</div>
              <div className="row-meta">
                {[document.category, document.owner_name, document.expires_at ? `vervalt ${shortDate(document.expires_at)}` : null].filter(Boolean).join(" · ")}
              </div>
              {document.location && <div className="row-description">Bewaarplek: {document.location}</div>}
              {document.reference && <div className="row-meta">Referentie: {document.is_sensitive ? "Gevoelige referentie opgeslagen" : document.reference}</div>}
              {document.notes && <div className="row-meta">{document.notes}</div>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {document.is_sensitive && <span className="status accent">Gevoelig</span>}
              {!readOnly && (
                <form action={deleteHouseholdDocument}>
                  <input type="hidden" name="id" value={document.id} />
                  <button className="icon-button" title="Document verwijderen" aria-label="Document verwijderen">
                    <Trash2 size={17} />
                  </button>
                </form>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HouseholdNoteList({ data, limit, readOnly = false }: { data: AppData; limit?: number; readOnly?: boolean }) {
  const notes = limit ? data.householdNotes.slice(0, limit) : data.householdNotes;
  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Prikbord</h2>
          <p className="muted">Korte gezinsberichten, reminders en mededelingen.</p>
        </div>
        <span className="status">{data.householdNotes.filter((note) => note.pinned).length} vast</span>
      </div>
      <ul className="list">
        {notes.length === 0 && <li className="empty-state">Nog geen berichten.</li>}
        {notes.map((note) => (
          <li className="list-row" key={note.id}>
            <div className="row-main">
              <div className="row-title">{note.title}</div>
              <div className="row-meta">
                {note.category} · {note.pinned ? "Vastgezet" : "Bericht"} · {note.expires_at ? `tot ${shortDate(note.expires_at)}` : shortDate(note.created_at)}
              </div>
              <div className="row-description">{note.body}</div>
            </div>
            {!readOnly && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <form action={toggleHouseholdNotePin}>
                  <input type="hidden" name="id" value={note.id} />
                  <input type="hidden" name="pinned" value={String(note.pinned)} />
                  <button className="button">{note.pinned ? "Losmaken" : "Vastzetten"}</button>
                </form>
                <form action={deleteHouseholdNote}>
                  <input type="hidden" name="id" value={note.id} />
                  <button className="icon-button" title="Bericht verwijderen" aria-label="Bericht verwijderen">
                    <Trash2 size={17} />
                  </button>
                </form>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MaintenanceList({ data, limit, readOnly = false }: { data: AppData; limit?: number; readOnly?: boolean }) {
  const items = limit ? data.maintenanceItems.slice(0, limit) : data.maintenanceItems;
  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Onderhoud</h2>
          <p className="muted">Terugkerende controles en huiszaken met vervaldatum.</p>
        </div>
        <span className="status">{data.maintenanceItems.filter((item) => item.status === "open").length} open</span>
      </div>
      <ul className="list">
        {items.length === 0 && <li className="empty-state">Nog geen onderhoud gepland.</li>}
        {items.map((item) => (
          <li className="list-row" key={item.id}>
            <div className="row-main">
              <div className="row-title" style={{ textDecoration: item.status === "done" ? "line-through" : undefined }}>{item.title}</div>
              <div className="row-meta">
                {[item.area, item.provider, shortDate(item.due_date), maintenanceFrequencyLabel(item.frequency)].filter(Boolean).join(" · ")}
              </div>
              {item.notes && <div className="row-description">{item.notes}</div>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className={maintenanceTone(item.due_date, item.status)}>{item.status === "done" ? "Gedaan" : "Open"}</span>
              {!readOnly && (
                <>
                  {item.status !== "done" && (
                    <form action={completeMaintenanceItem}>
                      <input type="hidden" name="id" value={item.id} />
                      <button className="icon-button" title="Afronden" aria-label="Afronden">
                        <Check size={17} />
                      </button>
                    </form>
                  )}
                  <form action={deleteMaintenanceItem}>
                    <input type="hidden" name="id" value={item.id} />
                    <button className="icon-button" title="Verwijderen" aria-label="Verwijderen">
                      <Trash2 size={17} />
                    </button>
                  </form>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function maintenanceFrequencyLabel(frequency: string) {
  if (frequency === "monthly") return "Maandelijks";
  if (frequency === "quarterly") return "Elk kwartaal";
  if (frequency === "yearly") return "Jaarlijks";
  return "Eenmalig";
}

function maintenanceTone(dueDate: string | null, status: string) {
  if (status === "done") return "status";
  if (dueDate && dueDate < new Date().toISOString().slice(0, 10)) return "status accent";
  return "status";
}

export function HouseholdContactList({ data, readOnly = false }: { data: AppData; readOnly?: boolean }) {
  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Belangrijke contacten</h2>
          <p className="muted">Huisarts, school, buren, oppas en noodnummers op een plek.</p>
        </div>
        <span className="status">{data.householdContacts.length}</span>
      </div>
      <ul className="list">
        {data.householdContacts.length === 0 && <li className="empty-state">Nog geen contacten.</li>}
        {data.householdContacts.map((contact) => (
          <li className="list-row" key={contact.id}>
            <div className="row-main">
              <div className="row-title">{contact.name}</div>
              <div className="row-meta">{[contact.relationship, priorityLabel(contact.priority)].filter(Boolean).join(" · ")}</div>
              {contact.notes && <div className="row-description">{contact.notes}</div>}
              <div className="contact-actions">
                {contact.phone && (
                  <a className="icon-link" href={`tel:${contact.phone}`} title="Bellen" aria-label={`${contact.name} bellen`}>
                    <Phone size={15} />
                    <span>{contact.phone}</span>
                  </a>
                )}
                {contact.email && (
                  <a className="icon-link" href={`mailto:${contact.email}`} title="Mailen" aria-label={`${contact.name} mailen`}>
                    <Mail size={15} />
                    <span>{contact.email}</span>
                  </a>
                )}
                {contact.address && (
                  <span className="icon-link">
                    <MapPin size={15} />
                    <span>{contact.address}</span>
                  </span>
                )}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className={contact.priority === "nood" ? "status accent" : "status"}>{priorityLabel(contact.priority)}</span>
              {!readOnly && (
                <form action={deleteHouseholdContact}>
                  <input type="hidden" name="id" value={contact.id} />
                  <button className="icon-button" title="Contact verwijderen" aria-label="Contact verwijderen">
                    <Trash2 size={17} />
                  </button>
                </form>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HouseholdInfoList({ data, readOnly = false }: { data: AppData; readOnly?: boolean }) {
  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Huisinformatie</h2>
          <p className="muted">Praktische gegevens die iedereen in huis snel moet kunnen vinden.</p>
        </div>
        <span className="status">{data.householdInfoItems.length}</span>
      </div>
      <ul className="list">
        {data.householdInfoItems.length === 0 && <li className="empty-state">Nog geen huisinformatie.</li>}
        {data.householdInfoItems.map((item) => (
          <li className="list-row" key={item.id}>
            <div className="row-main">
              <div className="row-title">{item.title}</div>
              <div className="row-meta">{item.category}</div>
              {item.value && <div className="row-description">{item.is_sensitive ? "Gevoelige informatie opgeslagen" : item.value}</div>}
              {item.notes && <div className="row-meta">{item.notes}</div>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {item.is_sensitive && <span className="status accent">Gevoelig</span>}
              {!readOnly && (
                <form action={deleteHouseholdInfoItem}>
                  <input type="hidden" name="id" value={item.id} />
                  <button className="icon-button" title="Info verwijderen" aria-label="Info verwijderen">
                    <Trash2 size={17} />
                  </button>
                </form>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function priorityLabel(priority: string) {
  if (priority === "nood") return "Nood";
  if (priority === "belangrijk") return "Belangrijk";
  return "Normaal";
}

export function WishlistItemList({
  data,
  limit,
  readOnly = false,
}: {
  data: AppData;
  limit?: number;
  readOnly?: boolean;
}) {
  const items = limit ? data.wishlistItems.slice(0, limit) : data.wishlistItems;
  const groups = groupWishlistItems(items);

  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Wishlist</h2>
          <p className="muted">Cadeauwensen, links en externe reserveringen.</p>
        </div>
        <span className="status">{data.wishlistItems.filter((item) => item.status === "open").length} open</span>
      </div>
      <div className="wishlist-family-summary">
        {groupWishlistItems(data.wishlistItems).map((group) => (
          <span className="status" key={group.owner}>
            {group.owner}: {group.items.filter((item) => item.status === "open").length}
          </span>
        ))}
        {data.wishlistItems.length === 0 && <span className="muted">Nog geen gezinswensen.</span>}
      </div>
      <div className="wishlist-group-list">
        {items.length === 0 && (
          <ModuleEmptyState
            icon={<Gift size={18} />}
            title="Nog geen wensen"
            detail="Voeg cadeauwensen toe en publiceer ze via een externe link voor familie of vrienden."
            actionHref={readOnly ? undefined : "/wishlist"}
            actionLabel="Wishlist openen"
          />
        )}
        {groups.map((group) => (
          <section className="wishlist-person-group" key={group.owner}>
            <div className="wishlist-person-head">
              <strong>{group.owner}</strong>
              <span>{group.items.length} wens{group.items.length === 1 ? "" : "en"}</span>
            </div>
            <ul className="list">
              {group.items.map((item) => (
                <WishlistItemRow item={item} readOnly={readOnly} key={item.id} />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

function WishlistItemRow({ item, readOnly }: { item: AppData["wishlistItems"][number]; readOnly: boolean }) {
  return (
    <li className="list-row wishlist-row">
      {item.image_url ? (
        <img src={item.image_url} alt="" className="wishlist-row-image" />
      ) : (
        <div className="wishlist-row-image placeholder">
          <Gift size={18} />
        </div>
      )}
      <div className="row-main">
        <div className="row-title" style={{ textDecoration: item.status === "purchased" ? "line-through" : undefined }}>{item.title}</div>
        <div className="row-meta">
          {[item.category, item.price_cents ? money(item.price_cents) : null].filter(Boolean).join(" · ")}
        </div>
        {item.description && <div className="row-description">{item.description}</div>}
        <div className="tag-list">
          <span className={wishlistStatusClass(item.status)}>{wishlistStatusLabel(item.status)}</span>
          <span className="status">{item.purchase_mode === "repeatable" ? "Herhaalbaar" : "Eenmalig"}</span>
          {item.purchase_count > 0 && <span className="status accent">{item.purchase_count}x gekocht</span>}
          <span className={item.is_public ? "status" : "status muted-status"}>{item.is_public ? "Extern zichtbaar" : "Prive"}</span>
          {item.reserved_by_name && <span className="status accent">Door {item.reserved_by_name}</span>}
          {item.url && (
            <a className="status" href={item.url} target="_blank" rel="noreferrer">
              <ExternalLink size={13} /> Link
            </a>
          )}
        </div>
      </div>
      {!readOnly && (
        <div className="wishlist-actions">
          {item.status !== "open" && (
            <form action={setWishlistItemStatus}>
              <input type="hidden" name="id" value={item.id} />
              <input type="hidden" name="status" value="open" />
              <button className="button">Open</button>
            </form>
          )}
          {(item.status === "open" || item.purchase_mode === "repeatable") && (
            <form action={setWishlistItemStatus}>
              <input type="hidden" name="id" value={item.id} />
              <input type="hidden" name="status" value="purchased" />
              <button className="icon-button" title="Afstrepen" aria-label="Afstrepen">
                <Check size={17} />
              </button>
            </form>
          )}
          <form action={toggleWishlistItemPublic}>
            <input type="hidden" name="id" value={item.id} />
            <input type="hidden" name="is_public" value={String(item.is_public)} />
            <button className="button">{item.is_public ? "Verbergen" : "Publiceren"}</button>
          </form>
          <form action={deleteWishlistItem}>
            <input type="hidden" name="id" value={item.id} />
            <button className="icon-button" title="Wens verwijderen" aria-label="Wens verwijderen">
              <Trash2 size={17} />
            </button>
          </form>
        </div>
      )}
    </li>
  );
}

function groupWishlistItems(items: AppData["wishlistItems"]) {
  const groups = new Map<string, AppData["wishlistItems"]>();
  for (const item of items) {
    const owner = item.desired_by?.trim() || "Huishouden";
    groups.set(owner, [...(groups.get(owner) ?? []), item]);
  }
  return [...groups.entries()].map(([owner, groupItems]) => ({ owner, items: groupItems }));
}

function wishlistStatusLabel(status: string) {
  if (status === "reserved") return "Gereserveerd";
  if (status === "purchased") return "Afgestreept";
  return "Open";
}

function wishlistStatusClass(status: string) {
  if (status === "open") return "status";
  if (status === "reserved") return "status accent";
  return "status muted-status";
}

export function TaskList({
  data,
  limit,
  tasks: providedTasks,
  readOnly = false,
}: {
  data: AppData;
  limit?: number;
  tasks?: AppData["tasks"];
  readOnly?: boolean;
}) {
  const sourceTasks = providedTasks ?? data.tasks;
  const subtasksByParent = data.tasks.reduce<Record<string, AppData["tasks"]>>((groups, task) => {
    if (!task.parent_task_id) return groups;
    groups[task.parent_task_id] = [...(groups[task.parent_task_id] ?? []), task];
    return groups;
  }, {});
  const parentTasks = sourceTasks.filter((task) => !task.parent_task_id);
  const tasks = limit ? parentTasks.slice(0, limit) : parentTasks;
  return (
    <ul className="list">
      {tasks.length === 0 && (
        <ModuleEmptyState
          icon={<CheckSquare size={18} />}
          title="Nog geen taken"
          detail="Leg de eerste taak vast, wijs hem toe aan een gezinslid en geef hem eventueel een deadline."
          actionHref={readOnly ? undefined : "/snel"}
          actionLabel="Taak toevoegen"
        />
      )}
      {tasks.map((task) => (
        <li className="list-row" key={task.id}>
          <div className="row-main">
            <div className="row-title" style={{ textDecoration: task.status === "done" ? "line-through" : undefined }}>{task.title}</div>
            {task.description && <div className="row-description">{task.description}</div>}
            <div className="row-meta">
              {memberName(task.assignee_id, data.members)} · {task.priority} · {shortDate(task.due_date)}
            </div>
            <div className="task-badges">
              {task.recurrence && task.recurrence !== "none" && <span className="status accent">{recurrenceLabel(task.recurrence)}</span>}
              {(subtasksByParent[task.id]?.length ?? 0) > 0 && <span className="status">{subtaskSummary(subtasksByParent[task.id])}</span>}
            </div>
            {!limit && (
              <div className="subtask-list">
                {(subtasksByParent[task.id] ?? []).map((subtask) => (
                  <div className="subtask-row" key={subtask.id}>
                    <form action={toggleTask}>
                      <input type="hidden" name="id" value={subtask.id} />
                      <input type="hidden" name="status" value={subtask.status} />
                      <button className="icon-button" title="Subtaak afvinken" aria-label="Subtaak afvinken">
                        <Check size={15} />
                      </button>
                    </form>
                    <span style={{ textDecoration: subtask.status === "done" ? "line-through" : undefined }}>{subtask.title}</span>
                    <form action={deleteTask}>
                      <input type="hidden" name="id" value={subtask.id} />
                      <button className="icon-button" title="Subtaak verwijderen" aria-label="Subtaak verwijderen">
                        <Trash2 size={15} />
                      </button>
                    </form>
                  </div>
                ))}
                {!readOnly && (
                  <form className="inline-form" action={addSubtask}>
                    <input type="hidden" name="parent_task_id" value={task.id} />
                    <input name="title" placeholder="Subtaak toevoegen" aria-label="Subtaak toevoegen" />
                    <button className="button">Toevoegen</button>
                  </form>
                )}
              </div>
            )}
          </div>
          {!readOnly && (
            <div style={{ display: "flex", gap: 8 }}>
              <form action={toggleTask}>
                <input type="hidden" name="id" value={task.id} />
                <input type="hidden" name="status" value={task.status} />
                <button className="icon-button" title="Status wisselen" aria-label="Status wisselen">
                  <Check size={17} />
                </button>
              </form>
              <form action={deleteTask}>
                <input type="hidden" name="id" value={task.id} />
                <button className="icon-button" title="Verwijderen" aria-label="Verwijderen">
                  <Trash2 size={17} />
                </button>
              </form>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function recurrenceLabel(recurrence: string) {
  if (recurrence === "daily") return "Dagelijks";
  if (recurrence === "weekly") return "Wekelijks";
  if (recurrence === "monthly") return "Maandelijks";
  return "Eenmalig";
}

function subtaskSummary(subtasks: AppData["tasks"]) {
  const done = subtasks.filter((task) => task.status === "done").length;
  return `${done}/${subtasks.length} subtaken`;
}

export function TaskIntegrationsPanel({ data }: { data: AppData }) {
  return (
    <div className="card">
      <h2>Koppelingen</h2>
      <ul className="list">
      {data.taskIntegrations.length === 0 && <li className="empty-state">Nog geen takenkoppelingen.</li>}
        {data.taskIntegrations.map((integration) => (
          <li className="list-row" key={integration.id}>
            <div>
              <div className="row-title">{integration.display_name}</div>
              <div className="row-meta">
                {integration.status} · {integration.sync_direction} · laatst gesynchroniseerd {shortDate(integration.last_sync_at)}
              </div>
            </div>
            <span className="status">{integration.provider === "apple_reminders" ? "Native bridge" : "Graph"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ShoppingListView({ data, limit, readOnly = false }: { data: AppData; limit?: number; readOnly?: boolean }) {
  const items = limit ? data.shoppingItems.slice(0, limit) : data.shoppingItems;
  return (
    <ul className="list">
      {items.length === 0 && (
        <ModuleEmptyState
          icon={<ShoppingBasket size={18} />}
          title="Nog geen boodschappen"
          detail="Voeg losse producten toe of zet ingrediënten vanuit Maaltijden direct op de gedeelde lijst."
          actionHref={readOnly ? undefined : "/snel"}
          actionLabel="Boodschap toevoegen"
        />
      )}
      {items.map((item) => (
        <li className="list-row" key={item.id}>
          <div className="row-main">
            <div className="row-title" style={{ textDecoration: item.checked ? "line-through" : undefined }}>{item.name}</div>
            <div className="row-meta">
              {[item.quantity, item.category].filter(Boolean).join(" · ") || "Geen details"}
            </div>
          </div>
          {!readOnly && (
            <div style={{ display: "flex", gap: 8 }}>
              <form action={toggleShoppingItem}>
                <input type="hidden" name="id" value={item.id} />
                <input type="hidden" name="checked" value={String(item.checked)} />
                <button className="icon-button" title="Afvinken" aria-label="Afvinken">
                  <Check size={17} />
                </button>
              </form>
              <form action={deleteShoppingItem}>
                <input type="hidden" name="id" value={item.id} />
                <button className="icon-button" title="Verwijderen" aria-label="Verwijderen">
                  <Trash2 size={17} />
                </button>
              </form>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ShoppingPriceComparisonPanel({ data }: { data: AppData }) {
  const comparison = buildBasketPriceComparison(data.shoppingItems, data.priceObservations);
  const completeStores = comparison.stores.filter((store) => store.missingItems === 0 && comparison.openItemCount > 0);
  const bestCompleteStore = completeStores.sort((a, b) => a.totalCents - b.totalCents)[0] ?? null;
  const bestStore = bestCompleteStore ?? comparison.bestStore;
  const provider = getShoppingPriceProviderStatus();
  const kauflandConfigured = hasKauflandProvider();
  const kauflandStore = comparison.stores.find((store) => store.storeId === "kaufland-de");
  const hasKauflandPrices = data.priceObservations.some((price) => price.store === "Kaufland DE" && price.price_provider === "apify");
  const missingPriceCount = comparison.stores.reduce((sum, store) => sum + store.missingItems, 0);
  const latestPriceCheckAt = data.priceObservations
    .filter((price) => price.source === "price_check")
    .reduce<string | null>((latest, price) => (!latest || price.observed_at > latest ? price.observed_at : latest), null);

  return (
    <div className="card shopping-price-check">
      <div className="section-head">
        <div>
          <h2>Prijscheck mandje</h2>
          <p className="muted">
            Dagelijkse vergelijking voor Lidl, Albert Heijn, Jumbo en Kaufland DE op basis van de open boodschappen.
          </p>
        </div>
        <span className={provider.configured ? "status" : "status accent"}>
          {provider.configured ? provider.label : "live prijzen uit"}
        </span>
      </div>

      {!provider.configured && (
        <div className="price-provider-note">
          <Store size={16} />
          <span>
            Live prijs ophalen is nog niet gekoppeld. Nieuwe producten zoals komkommer krijgen pas actuele prijzen zodra een provider-token is ingesteld; tot die tijd gebruikt de app alleen bekende prijzen uit scans of handmatige invoer.
          </span>
        </div>
      )}

      {provider.configured && missingPriceCount > 0 && (
        <div className="price-provider-note">
          <Store size={16} />
          <span>{missingPriceCount} prijsregels ontbreken nog. De dagelijkse sync vult deze aan zodra de provider een match vindt.</span>
        </div>
      )}

      {provider.configured && !kauflandConfigured && (kauflandStore?.missingItems ?? 0) > 0 && (
        <div className="price-provider-note">
          <Store size={16} />
          <span>Kaufland DE is voorbereid via Apify, maar haalt pas live prijzen op zodra `APIFY_TOKEN` op de server is ingevuld.</span>
        </div>
      )}

      {provider.configured && kauflandConfigured && !hasKauflandPrices && (kauflandStore?.missingItems ?? 0) > 0 && (
        <div className="price-provider-note">
          <Store size={16} />
          <span>Kaufland DE is gekoppeld als testbron, maar de huidige Apify actor levert nog geen productregels terug voor deze zoekopdrachten.</span>
        </div>
      )}

      <div className="price-updated-row">
        <span>Laatste prijscheck: {latestPriceCheckAt ? shortDate(latestPriceCheckAt) : "nog niet uitgevoerd"}</span>
        {comparison.lastUpdatedAt && latestPriceCheckAt !== comparison.lastUpdatedAt && <span>Laatste prijsobservatie: {shortDate(comparison.lastUpdatedAt)}</span>}
      </div>

      <div className="price-store-grid">
        {comparison.stores.map((store) => (
          <div className={bestStore?.storeId === store.storeId ? "price-store-card best" : "price-store-card"} key={store.storeId}>
            <div>
              <strong>{store.storeLabel}</strong>
              <span>{store.country}</span>
            </div>
            <b>{store.pricedItems ? money(store.totalCents) : "n.n.b."}</b>
            <small>
              {store.pricedItems}/{comparison.openItemCount || 0} items
              {store.offers > 0 ? ` · ${store.offers} aanbieding${store.offers === 1 ? "" : "en"}` : ""}
            </small>
            {store.missingItems > 0 && <em>{store.missingItems} mist prijs</em>}
          </div>
        ))}
      </div>

      {comparison.offers.length > 0 ? (
        <div className="price-offer-box">
          <div className="price-box-title">
            <BadgePercent size={16} />
            <strong>Aanbiedingen in je mandje</strong>
          </div>
          <ul>
            {comparison.offers.slice(0, 5).map((offer) => (
              <li key={`${offer.itemName}-${offer.storeLabel}-${offer.price.id}`}>
                <span>{offer.itemName}</span>
                <a
                  className={offer.price.external_url ? "price-product-link" : "price-product-link disabled"}
                  href={offer.price.external_url ?? undefined}
                  target="_blank"
                  rel="noreferrer"
                  aria-disabled={!offer.price.external_url}
                >
                  {offer.storeLabel} · {money(offer.price.total_price_cents)}
                  {offer.price.regular_price_cents ? ` i.p.v. ${money(offer.price.regular_price_cents)}` : ""}
                  {offer.price.offer_label ? ` · ${offer.price.offer_label}` : ""}
                  {offer.price.matched_product_name ? ` · ${offer.price.matched_product_name}` : ""}
                  {offer.price.price_provider ? ` · ${priceProviderLabel(offer.price.price_provider)}` : ""}
                  {offer.price.external_url && <ExternalLink size={12} />}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="price-offer-empty">
          <BadgePercent size={16} />
          <span>Geen aanbiedingen bekend voor de huidige mandje-items.</span>
        </div>
      )}

      <div className="price-compare-grid" role="table" aria-label="Prijsvergelijking boodschappen">
        <div className="price-grid-row price-grid-head" role="row">
          <div className="price-grid-item-cell" role="columnheader">
            Item
          </div>
          {comparison.stores.map((store) => (
            <div className="price-grid-store-head" role="columnheader" key={store.storeId}>
              <span className={`store-logo-badge store-logo-${store.storeId}`} title={store.storeLabel} aria-label={store.storeLabel}>
                {storeLogoLabel(store.storeId, store.storeLabel)}
              </span>
            </div>
          ))}
        </div>

        {comparison.rows.length === 0 ? (
          <div className="empty-state price-grid-empty">Geen open boodschappen om te vergelijken.</div>
        ) : (
          comparison.rows.slice(0, 8).map((row) => (
            <div className="price-grid-row" role="row" key={row.item.id}>
              <div className="price-grid-item-cell" role="cell">
                <strong>{row.item.name}</strong>
                <span>{row.item.quantity ?? row.item.category ?? "Mandje-item"}</span>
              </div>
              {row.prices.map((price) => (
                <div className={row.cheapest?.storeId === price.storeId ? "price-grid-price-cell cheapest" : "price-grid-price-cell"} role="cell" key={price.storeId}>
                  {price.price ? (
                    <>
                      <strong>{money(price.price.total_price_cents)}</strong>
                      <span>{price.price.quantity ?? priceProviderLabel(price.price.price_provider ?? "")}</span>
                      {price.price.external_url ? (
                        <a
                          className="price-grid-link"
                          href={price.price.external_url}
                          target="_blank"
                          rel="noreferrer"
                          title={`${price.storeLabel} product bekijken`}
                          aria-label={`${price.storeLabel} product bekijken`}
                        >
                          <ExternalLink size={13} />
                        </a>
                      ) : (
                        <span className="price-grid-link disabled" aria-hidden="true">
                          <ExternalLink size={13} />
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="price-grid-missing">-</span>
                  )}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function MealPlanList({ data, limit, readOnly = false }: { data: AppData; limit?: number; readOnly?: boolean }) {
  const meals = limit ? data.mealPlans.slice(0, limit) : data.mealPlans;
  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Maaltijdplanning</h2>
          <p className="muted">Plan eten vooruit en zet ingrediënten direct op de boodschappenlijst.</p>
        </div>
        <span className="status">{data.mealPlans.length}</span>
      </div>
      <ul className="list">
        {meals.length === 0 && <li className="empty-state">Nog geen maaltijden gepland.</li>}
        {meals.map((meal) => {
          const ingredients = splitIngredients(meal.ingredients);
          return (
            <li className="list-row" key={meal.id}>
              <div className="row-main">
                <div className="row-title">{meal.title}</div>
                <div className="row-meta">
                  {shortDate(meal.planned_date)} · {mealTypeLabel(meal.meal_type)} · {ingredients.length} ingrediënten
                </div>
                {meal.notes && <div className="row-description">{meal.notes}</div>}
                {ingredients.length > 0 && (
                  <div className="tag-list">
                    {ingredients.slice(0, 6).map((ingredient) => (
                      <span className="tag" key={ingredient}>{ingredient}</span>
                    ))}
                  </div>
                )}
              </div>
              {!readOnly && (
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <form action={addMealIngredientsToShopping}>
                    <input type="hidden" name="id" value={meal.id} />
                    <button className="button">Naar lijst</button>
                  </form>
                  <form action={deleteMealPlan}>
                    <input type="hidden" name="id" value={meal.id} />
                    <button className="icon-button" title="Maaltijd verwijderen" aria-label="Maaltijd verwijderen">
                      <Trash2 size={17} />
                    </button>
                  </form>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function splitIngredients(ingredients: string | null) {
  return (ingredients ?? "")
    .split(/\r?\n|,/)
    .map((ingredient) => ingredient.trim())
    .filter(Boolean);
}

function mealTypeLabel(mealType: string) {
  if (mealType === "ontbijt") return "Ontbijt";
  if (mealType === "lunch") return "Lunch";
  if (mealType === "snack") return "Snack";
  return "Avondeten";
}

export function SmartShoppingPanel({ data }: { data: AppData }) {
  const recurring = data.shoppingProducts.filter((product) => product.recurrence !== "none").slice(0, 6);
  const topProducts = data.shoppingProducts.slice(0, 6);

  return (
    <div className="grid">
      <div className="card">
        <h2>Terugkerend</h2>
        <ul className="list">
          {recurring.length === 0 && <li className="empty-state">Nog geen terugkerende producten.</li>}
          {recurring.map((product) => (
            <li className="list-row" key={product.id}>
              <div>
                <div className="row-title">{product.name}</div>
                <div className="row-meta">
                  {product.recurrence} · {product.default_quantity ?? "Geen standaardhoeveelheid"} · {product.purchase_count}x gekocht
                </div>
              </div>
              <span className="status">{product.category ?? "Algemeen"}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h2>Vaak gekocht</h2>
        <ul className="list">
          {topProducts.length === 0 && <li className="empty-state">Nog geen productgeschiedenis.</li>}
          {topProducts.map((product) => (
            <li className="list-row" key={product.id}>
              <div>
                <div className="row-title">{product.name}</div>
                <div className="row-meta">
                  {product.purchase_count} aankopen · laatst {shortDate(product.last_purchased_at)}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function PriceHistoryPanel({ data }: { data: AppData }) {
  const insights = buildPriceInsights(data.priceObservations);

  return (
    <div className="grid">
      <div className="card">
        <h2>Prijsinzicht</h2>
        <ul className="list">
          {insights.length === 0 && <li className="empty-state">Voeg minimaal twee prijzen van een product toe om trendinformatie te zien.</li>}
          {insights.map((item) => (
            <li className="list-row price-insight-row" key={item.name}>
              <div className="row-main">
                <div className="row-title">{item.name}</div>
                <div className="row-meta">
                  Laatste {money(item.latest)} · laagste {money(item.lowest)} · gemiddeld {money(item.average)}
                </div>
                <div className="price-meter" aria-label={`${item.name} prijspositie`}>
                  <span style={{ width: `${item.position}%` }} />
                </div>
              </div>
              <span className={item.delta > 0 ? "status accent" : "status"}>{item.deltaLabel}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h2>Prijshistorie</h2>
        <ul className="list">
          {data.priceObservations.length === 0 && <li className="empty-state">Nog geen prijzen geregistreerd.</li>}
          {data.priceObservations.slice(0, 8).map((price) => (
            <li className="list-row" key={price.id}>
              <div className="row-main">
                <div className="row-title">{price.product_name}</div>
                <div className="row-meta">
                  {price.store ?? "Onbekende winkel"} · {shortDate(price.observed_at)} · {price.quantity ?? "Geen hoeveelheid"} · {price.source}
                </div>
              </div>
              <span className="status">{money(price.total_price_cents)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function ShoppingScansPanel({ data }: { data: AppData }) {
  return (
    <div className="card">
      <h2>Foto/OCR checks</h2>
      <ul className="list">
        {data.shoppingScans.length === 0 && <li className="empty-state">Nog geen bonnen of productfoto scans.</li>}
        {data.shoppingScans.map((scan) => (
          <li className="list-row" key={scan.id}>
            <div className="row-main">
              <div className="row-title">{scan.source_filename ?? "Scan"}</div>
              <div className="row-meta">
                {scan.status} · {shortDate(scan.created_at)}
              </div>
            </div>
            <span className="status">{scan.extracted_text ? "Tekst gevonden" : "Review"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function FinanceList({ data, limit, readOnly = false }: { data: AppData; limit?: number; readOnly?: boolean }) {
  const items = limit ? data.financeItems.slice(0, limit) : data.financeItems;
  return (
    <ul className="list">
      {items.length === 0 && (
        <ModuleEmptyState
          icon={<Landmark size={18} />}
          title="Nog geen gelditems"
          detail="Begin met vaste lasten, abonnementen of een komende betaling zodat het maandbeeld klopt."
          actionHref={readOnly ? undefined : "/snel"}
          actionLabel="Betaalmoment toevoegen"
        />
      )}
      {items.map((item) => (
        <li className="list-row" key={item.id}>
          <div className="row-main">
            <div className="row-title">{item.title}</div>
            <div className="row-meta">
              {item.category} · {item.frequency} · {shortDate(item.due_date)} · {item.status}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="status">{money(item.amount_cents)}</span>
            {!readOnly && (
              <>
                {item.status !== "betaald" && (
                  <form action={markFinanceItemPaid}>
                    <input type="hidden" name="id" value={item.id} />
                    <button className="button">Betaald</button>
                  </form>
                )}
                <form action={deleteFinanceItem}>
                  <input type="hidden" name="id" value={item.id} />
                  <button className="icon-button" title="Verwijderen" aria-label="Verwijderen">
                    <Trash2 size={17} />
                  </button>
                </form>
              </>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function FinanceBudgetOverview({ data, readOnly = false }: { data: AppData; readOnly?: boolean }) {
  const monthlyByCategory = data.financeItems.reduce<Record<string, number>>((totals, item) => {
    if (item.status !== "actief") return totals;
    const amount = item.frequency === "jaarlijks" ? Math.round(item.amount_cents / 12) : item.amount_cents;
    if (item.frequency === "eenmalig") return totals;
    totals[item.category] = (totals[item.category] ?? 0) + amount;
    return totals;
  }, {});
  const unbudgetedTotal = Object.entries(monthlyByCategory)
    .filter(([category]) => !data.financeBudgets.some((budget) => budget.category === category))
    .reduce((sum, [, amount]) => sum + amount, 0);

  return (
    <div className="card">
      <h2>Budgetten</h2>
      <div className="budget-summary">
        <div>
          <div className="metric">{money(data.financeBudgets.reduce((sum, budget) => sum + budget.monthly_limit_cents, 0))}</div>
          <p className="muted">Totaal maandbudget</p>
        </div>
        <div>
          <div className="metric">{money(Object.values(monthlyByCategory).reduce((sum, amount) => sum + amount, 0))}</div>
          <p className="muted">Bekende maandlasten</p>
        </div>
      </div>
      <ul className="list">
        {data.financeBudgets.length === 0 && <li className="empty-state">Nog geen budgetten. Maak budgetten per categorie om grip te krijgen op de maand.</li>}
        {data.financeBudgets.map((budget) => {
          const spent = monthlyByCategory[budget.category] ?? 0;
          const ratio = budget.monthly_limit_cents > 0 ? spent / budget.monthly_limit_cents : 0;
          const warning = ratio >= Number(budget.alert_threshold);
          return (
            <li className="list-row" key={budget.id}>
              <div className="row-main">
                <div className="row-title">{budget.category}</div>
                <div className="progress-track" aria-label={`${budget.category} budget gebruikt`}>
                  <span className={warning ? "progress-fill warning" : "progress-fill"} style={{ width: `${Math.min(100, Math.round(ratio * 100))}%` }} />
                </div>
                <div className="row-meta">
                  {money(spent)} van {money(budget.monthly_limit_cents)} · waarschuwing vanaf {Math.round(Number(budget.alert_threshold) * 100)}%
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className={warning ? "status accent" : "status"}>{Math.round(ratio * 100)}%</span>
                {!readOnly && (
                  <form action={deleteFinanceBudget}>
                    <input type="hidden" name="id" value={budget.id} />
                    <button className="icon-button" title="Budget verwijderen" aria-label="Budget verwijderen">
                      <Trash2 size={17} />
                    </button>
                  </form>
                )}
              </div>
            </li>
          );
        })}
        {unbudgetedTotal > 0 && (
          <li className="list-row">
            <div>
              <div className="row-title">Zonder budget</div>
              <div className="row-meta">Categorieen met vaste lasten zonder maandbudget</div>
            </div>
            <span className="status accent">{money(unbudgetedTotal)}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

export function RecurringCostsPanel({ data }: { data: AppData }) {
  const insights = buildRecurringCostInsights(data, new Date().toISOString(), 80);
  const trend = buildRecurringCashflowTrend(data, new Date().toISOString(), 6);

  return (
    <div className="card recurring-costs-card">
      <RecurringCostGroups insights={insights} trend={trend} />
    </div>
  );
}

export function BankOverview({ data }: { data: AppData }) {
  const balance = data.bankAccounts.reduce((sum, account) => sum + (account.balance_cents ?? 0), 0);
  return (
    <div className="card">
      <h2>Bank</h2>
      {data.bankConnections.length === 0 ? (
        <p className="empty-state">Nog geen bankkoppeling.</p>
      ) : (
        <div className="grid">
          <div>
            <div className="metric">{money(balance)}</div>
            <p className="muted">Totaal bekend banksaldo</p>
          </div>
          <ul className="list">
            {data.bankConnections.map((connection) => (
              <li className="list-row" key={connection.id}>
                <div>
                  <div className="row-title">{bankProviderLabel(connection.provider)} {connection.environment}</div>
                  <div className="row-meta">
                    {connection.status} · laatst gesynchroniseerd {shortDate(connection.last_sync_at)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function bankProviderLabel(provider: string) {
  if (provider === "abn_amro_manual") return "ABN AMRO import";
  if (provider === "bunq") return "bunq";
  return provider;
}

export function BankAccountsList({ data }: { data: AppData }) {
  return (
    <div className="card">
      <h2>Rekeningen</h2>
      <ul className="list">
        {data.bankAccounts.length === 0 && <li className="empty-state">Nog geen rekeningen opgehaald.</li>}
        {data.bankAccounts.map((account) => (
          <li className="list-row" key={account.id}>
            <div>
              <div className="row-title">{account.name}</div>
              <div className="row-meta">{account.iban ?? account.provider_account_id}</div>
            </div>
            <span className="status">{account.balance_cents === null ? account.currency : money(account.balance_cents)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BankTransactionsList({ data, limit = 25 }: { data: AppData; limit?: number }) {
  const transactions = data.bankTransactions.slice(0, limit);
  const accountsById = new Map(data.bankAccounts.map((account) => [account.id, account]));
  const hiddenCount = Math.max(0, data.bankTransactions.length - transactions.length);
  return (
    <div className="card">
      <h2>Recente transacties</h2>
      <ul className="list bank-transactions-list">
        {transactions.length === 0 && <li className="empty-state">Nog geen transacties opgehaald.</li>}
        {transactions.map((transaction) => {
          const account = transaction.account_id ? accountsById.get(transaction.account_id) : null;
          const detailTags = transactionDetailTags(transaction);
          const title = cleanTransactionTitle(transaction.description);
          return (
            <li className="list-row bank-transaction-row" key={transaction.id}>
              <div className="row-main">
                <div className="row-title">{title}</div>
                <div className="row-meta">
                  {shortDate(transaction.booked_at)} · {account?.name ?? "Onbekende rekening"} · {transaction.counterparty ?? "Onbekend"} ·{" "}
                  {transaction.category ?? "Ongecategoriseerd"}
                </div>
                {detailTags.length > 0 && (
                  <div className="transaction-detail-tags">
                    {detailTags.map((tag) => (
                      <span className="transaction-detail-tag" key={`${transaction.id}-${tag.label}-${tag.value}`}>
                        <strong>{tag.label}</strong>
                        {tag.value}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <span className={transaction.amount_cents < 0 ? "status amount-status negative" : "status amount-status positive"}>
                {money(transaction.amount_cents)}
              </span>
              {transaction.amount_cents < 0 && (
                <form action={setRecurringTransactionRule}>
                  <input type="hidden" name="transaction_id" value={transaction.id} />
                  <input type="hidden" name="rule_action" value="force_recurring" />
                  <button className="button compact-button">Markeer terugkerend</button>
                </form>
              )}
            </li>
          );
        })}
        {hiddenCount > 0 && <li className="empty-state">Nog {hiddenCount} transacties verborgen. Gebruik zoeken of filters om te verfijnen.</li>}
      </ul>
    </div>
  );
}

function transactionDetailTags(transaction: AppData["bankTransactions"][number]) {
  const source = `${transaction.description} ${rawText(transaction.raw)}`;
  const tags: Array<{ label: string; value: string }> = [];
  const sepaFields = parseSlashFields(source);
  const type = matchPaymentType(source);
  if (type) tags.push({ label: "Type", value: type });
  if (sepaFields.CSID) tags.push({ label: "CSID", value: sepaFields.CSID });
  if (sepaFields.MARF) tags.push({ label: "Mandaat", value: sepaFields.MARF });
  if (sepaFields.REMI) tags.push({ label: "Ref", value: sepaFields.REMI });
  const pass = source.match(/\bPAS\s*([A-Z0-9]{2,})\b/i) ?? source.match(/\bPAS([A-Z0-9]{2,})\b/i);
  if (pass?.[1]) tags.push({ label: "Pas", value: pass[1].toUpperCase() });
  const nr = source.match(/\b(?:NR|TRANSACTIENR|TRANSACTIENUMMER|KENMERK)[:\s]*([A-Z0-9-]{3,})\b/i);
  if (nr?.[1]) tags.push({ label: "Nr", value: nr[1].toUpperCase() });
  const time = source.match(/\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\/\d{1,2}:\d{2})\b/);
  if (time?.[1]) tags.push({ label: "Moment", value: time[1] });
  const location = source.match(/\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\/\d{1,2}:\d{2}\s+([A-Z][A-Z\s.'-]{2,})\b/);
  if (location?.[1]) tags.push({ label: "Locatie", value: titleCase(location[1]) });
  return dedupeTags(tags).slice(0, 5);
}

function cleanTransactionTitle(description: string) {
  const sepaName = parseSlashFields(description).NAME;
  if (sepaName) return titleCase(sepaName);
  const cleaned = description
    .replace(/\bBEA,\s*/i, "")
    .replace(/\bApple Pay\s+/i, "")
    .replace(/,?\s*PAS\s*[A-Z0-9]{2,}\b/gi, "")
    .replace(/\bPAS[A-Z0-9]{2,}\b/gi, "")
    .replace(/\b(?:NR|TRANSACTIENR|TRANSACTIENUMMER|KENMERK)[:\s]*[A-Z0-9-]{3,}\b/gi, "")
    .replace(/,?\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\/\d{1,2}:\d{2}\s+[A-Z][A-Z\s.'-]{2,}\b/g, "")
    .replace(/\s*,\s*,/g, ",")
    .replace(/^[,\s]+|[,\s]+$/g, "")
    .replace(/\s{2,}/g, " ");
  return cleaned || description;
}

function parseSlashFields(input: string) {
  const fields: Record<string, string> = {};
  const pattern = /\/([A-Z]{2,5})\/([^/]*?)(?=\/[A-Z]{2,5}\/|$)/gi;
  for (const match of input.matchAll(pattern)) {
    const key = match[1]?.toUpperCase();
    const value = match[2]?.trim();
    if (key && value && !fields[key]) fields[key] = value;
  }
  return fields;
}

function matchPaymentType(input: string) {
  const known = [
    ["APPLE PAY", "Apple Pay"],
    ["SEPA", "SEPA"],
    ["IDEAL", "iDEAL"],
    ["BEA", "Betaalautomaat"],
    ["BETAALAUTOMAAT", "Betaalautomaat"],
    ["INCASSO", "Incasso"],
    ["CREDITRENTE", "Rente"],
    ["DIRECT SPAREN", "Direct Sparen"],
  ] as const;
  const upper = input.toUpperCase();
  return known.find(([needle]) => upper.includes(needle))?.[1] ?? null;
}

function rawText(raw: unknown) {
  if (!raw || typeof raw !== "object") return "";
  return Object.values(raw as Record<string, unknown>)
    .filter((value) => typeof value === "string" || typeof value === "number")
    .join(" ");
}

function titleCase(input: string) {
  return input
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function dedupeTags(tags: Array<{ label: string; value: string }>) {
  const seen = new Set<string>();
  return tags.filter((tag) => {
    const key = `${tag.label}:${tag.value}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function CalendarList({ data, limit, readOnly = false }: { data: AppData; limit?: number; readOnly?: boolean }) {
  const items = limit ? data.calendarEvents.slice(0, limit) : data.calendarEvents;
  return (
    <ul className="list">
      {items.length === 0 && (
        <ModuleEmptyState
          icon={<CalendarDays size={18} />}
          title="Nog geen afspraken"
          detail="Zet de eerste gezinsafspraak erin of koppel Outlook of een ICS-agenda zodat alles samen zichtbaar wordt."
          actionHref={readOnly ? undefined : "/snel"}
          actionLabel="Afspraak toevoegen"
        />
      )}
      {items.map((event) => (
        <li className="list-row" key={event.id}>
          <div className="row-main">
            <div className="row-title">{event.title}</div>
            <div className="row-meta">
              {shortDate(event.starts_at)} · {event.location || "Geen locatie"} ·{" "}
              {calendarSourceLabel(event)}
              {event.organizer_name ? ` · ${event.organizer_name}` : ""}
            </div>
          </div>
          {event.source_provider ? (
            <span className="status">Gesynchroniseerd</span>
          ) : !readOnly ? (
            <form action={deleteCalendarEvent}>
              <input type="hidden" name="id" value={event.id} />
              <button className="icon-button" title="Verwijderen" aria-label="Verwijderen">
                <Trash2 size={17} />
              </button>
            </form>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function BirthdayCalendarCard({ data, readOnly = false }: { data: AppData; readOnly?: boolean }) {
  const today = startOfToday();
  const birthdays = (data.householdBirthdays ?? [])
    .map((birthday) => {
      const next = nextBirthdayDate(birthday.birth_date, today);
      return {
        birthday,
        next,
        daysUntil: Math.round((next.getTime() - today.getTime()) / 86_400_000),
        nextAge: next.getUTCFullYear() - birthdayYear(birthday.birth_date),
      };
    })
    .sort((left, right) => left.next.getTime() - right.next.getTime())
    .slice(0, 6);

  return (
    <section className="birthday-calendar card">
      <div className="section-head">
        <div>
          <h2>Aankomende verjaardagen</h2>
          <p className="muted">Jaarlijks bijgewerkt voor je gezin en naasten.</p>
        </div>
        <span className="status">{data.householdBirthdays?.length ?? 0}</span>
      </div>
      <ul className="birthday-list">
        {birthdays.length === 0 && <li className="birthday-empty">Nog geen verjaardagen toegevoegd.</li>}
        {birthdays.map(({ birthday, next, daysUntil, nextAge }) => (
          <li className="birthday-row" key={birthday.id}>
            <time dateTime={next.toISOString().slice(0, 10)}>
              <strong>{new Intl.DateTimeFormat("nl-NL", { day: "numeric" }).format(next)}</strong>
              <span>{new Intl.DateTimeFormat("nl-NL", { month: "short" }).format(next)}</span>
            </time>
            <span className="birthday-icon"><Gift size={16} /></span>
            <div className="birthday-main">
              <strong>{birthday.name}</strong>
              <span>{[birthday.relation, nextAge > 0 ? `wordt ${nextAge}` : null, birthday.notes].filter(Boolean).join(" · ") || "Verjaardag"}</span>
            </div>
            <span className="birthday-when">{birthdayRelativeLabel(daysUntil)}</span>
            {!readOnly && (
              <form action={deleteHouseholdBirthday}>
                <input type="hidden" name="id" value={birthday.id} />
                <button className="icon-button" title="Verjaardag verwijderen" aria-label="Verjaardag verwijderen">
                  <Trash2 size={17} />
                </button>
              </form>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function startOfToday() {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
}

function nextBirthdayDate(birthDate: string | Date, today: Date) {
  const [year, month, day] = birthdayParts(birthDate);
  const birthdayForYear = (targetYear: number) => {
    const isLeapDay = month === 2 && day === 29;
    const leapYear = targetYear % 4 === 0 && (targetYear % 100 !== 0 || targetYear % 400 === 0);
    return new Date(Date.UTC(targetYear, month - 1, isLeapDay && !leapYear ? 28 : day));
  };
  const current = birthdayForYear(today.getUTCFullYear());
  return current < today ? birthdayForYear(today.getUTCFullYear() + 1) : current;
}

function birthdayYear(birthDate: string | Date) {
  return birthdayParts(birthDate)[0];
}

function birthdayParts(birthDate: string | Date) {
  const value = birthDate instanceof Date ? birthDate.toISOString().slice(0, 10) : birthDate;
  const parts = value.split("-").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return [0, 1, 1] as const;
  return parts as [number, number, number];
}

function birthdayRelativeLabel(daysUntil: number) {
  if (daysUntil === 0) return "Vandaag";
  if (daysUntil === 1) return "Morgen";
  return `Over ${daysUntil} dagen`;
}

function calendarSourceLabel(event: AppData["calendarEvents"][number]) {
  if (!event.source_provider) return "Gezin";
  if (event.external_calendar_name) return event.external_calendar_name;
  return event.source_provider === "ics" ? "ICS agenda" : "Outlook";
}

function ModuleEmptyState({
  icon,
  title,
  detail,
  actionHref,
  actionLabel,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  actionHref?: string;
  actionLabel?: string;
}) {
  return (
    <li className="empty-state module-empty-state">
      <span className="module-empty-icon">{icon}</span>
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
      {actionHref && actionLabel && (
        <a className="button" href={actionHref}>
          <Plus size={16} /> {actionLabel}
        </a>
      )}
    </li>
  );
}

export function CalendarIntegrationsPanel({ data }: { data: AppData }) {
  const icsSubscriptions = data.icsCalendarSubscriptions ?? [];
  const icsFileImports = data.icsCalendarFileImports ?? [];
  return (
    <div className="card">
      <h2>Agenda-koppelingen</h2>
      <ul className="list">
        {data.calendarIntegrations.length === 0 && icsSubscriptions.length === 0 && icsFileImports.length === 0 && <li className="muted">Nog geen agenda-koppeling toegevoegd.</li>}
        {data.calendarIntegrations.map((integration) => (
          <li className="list-row" key={integration.id}>
            <div>
              <div className="row-title">{integration.display_name}</div>
              <div className="row-meta">
                {integration.account_email ?? "Account nog onbekend"} · {integration.status} · laatst gesynchroniseerd{" "}
                {shortDate(integration.last_sync_at)}
              </div>
            </div>
            <OutlookCalendarActions integration={integration} />
          </li>
        ))}
        {icsSubscriptions.map((subscription) => (
          <li className="list-row" key={subscription.id}>
            <div>
              <div className="row-title">{subscription.display_name}</div>
              <div className="row-meta">
                ICS-abonnement · {subscription.status} · laatst gesynchroniseerd {shortDate(subscription.last_sync_at)}
              </div>
            </div>
            <div className="integration-actions">
              <IcsCalendarActions subscription={subscription} />
              <form action={deleteIcsCalendarSource}>
                <input type="hidden" name="id" value={subscription.id} />
                <input type="hidden" name="kind" value="subscription" />
                <button className="icon-button" title="ICS-abonnement verwijderen" aria-label="ICS-abonnement verwijderen">
                  <Trash2 size={17} />
                </button>
              </form>
            </div>
          </li>
        ))}
        {icsFileImports.map((imported) => (
          <li className="list-row" key={imported.id}>
            <div>
              <div className="row-title">{imported.display_name}</div>
              <div className="row-meta">
                ICS-bestand · {imported.file_name} · geimporteerd {shortDate(imported.last_imported_at)}
              </div>
            </div>
            <div className="integration-actions">
              <span className="status">{imported.status}</span>
              <form action={deleteIcsCalendarSource}>
                <input type="hidden" name="id" value={imported.id} />
                <input type="hidden" name="kind" value="file" />
                <button className="icon-button" title="ICS-bestand en afspraken verwijderen" aria-label="ICS-bestand en afspraken verwijderen">
                  <Trash2 size={17} />
                </button>
              </form>
            </div>
          </li>
        ))}
      </ul>
      <p className="muted" style={{ marginBottom: 0 }}>
        Outlook, ICS-abonnementen en geimporteerde ICS-bestanden komen samen in de gezinsagenda. ICS-links blijven server-side en worden nooit in de app getoond.
      </p>
    </div>
  );
}

function buildPriceInsights(prices: PriceObservation[]) {
  const groups = prices.reduce<Record<string, PriceObservation[]>>((collection, price) => {
    const key = price.product_name.trim().toLocaleLowerCase("nl-NL");
    if (!key) return collection;
    collection[key] = [...(collection[key] ?? []), price];
    return collection;
  }, {});

  return Object.values(groups)
    .map((items) => {
      const sorted = [...items].sort((a, b) => new Date(b.observed_at).getTime() - new Date(a.observed_at).getTime());
      const latest = sorted[0];
      const previous = sorted[1];
      const totals = sorted.map((item) => item.total_price_cents);
      const lowest = Math.min(...totals);
      const highest = Math.max(...totals);
      const average = Math.round(totals.reduce((sum, value) => sum + value, 0) / totals.length);
      const delta = previous ? latest.total_price_cents - previous.total_price_cents : 0;
      const position = highest === lowest ? 8 : Math.max(8, Math.min(100, Math.round(((latest.total_price_cents - lowest) / (highest - lowest)) * 100)));
      return {
        name: latest.product_name,
        count: sorted.length,
        latest: latest.total_price_cents,
        lowest,
        average,
        delta,
        deltaLabel: delta === 0 ? "Stabiel" : `${delta > 0 ? "+" : ""}${money(delta)}`,
        position,
      };
    })
    .filter((item) => item.count >= 2)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta) || b.count - a.count)
    .slice(0, 6);
}

function priceProviderLabel(provider: string) {
  if (provider === "checkjebon") return "Checkjebon";
  if (provider === "prijsprofeet") return "PrijsProfeet";
  if (provider === "apify") return "Apify";
  if (provider === "webscraping_amsterdam") return "Managed feed";
  return provider;
}

function storeLogoLabel(storeId: string, storeLabel: string) {
  if (storeId === "albert-heijn") return "AH";
  if (storeId === "jumbo") return "J";
  if (storeId === "lidl") return "L";
  if (storeId === "kaufland-de") return "K";
  return storeLabel.slice(0, 2).toUpperCase();
}
