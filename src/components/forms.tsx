import {
  CalendarDays,
  Landmark,
  MessageSquare,
  ShoppingBasket,
  Trash2,
  Utensils,
} from "lucide-react";
import type { ReactNode } from "react";
import {
  addHouseholdContact,
  addAddressBookContact,
  addAddressBookMember,
  addHouseholdBirthday,
  addHouseholdDocument,
  addHouseholdInfoItem,
  addHouseholdNote,
  addCalendarEvent,
  addFinanceBudget,
  addFinanceItem,
  addMealPlan,
  addMaintenanceItem,
  addShoppingItem,
  addTask,
  addWishlistItem,
  importAbnAmroStatement,
  importAddressBookContacts,
  quickAdd,
  saveBunqConnection,
  saveGoogleHomeIntegration,
  saveHomeAssistantConfig,
  saveHueConfig,
  importIcsCalendarFile,
  saveIcsCalendarSubscription,
  saveOutlookOAuthConfig,
  saveTaskIntegration,
} from "@/app/actions";
import { BunqSubmitButton } from "@/components/bunq-actions";
import { AddressBookFamilyPicker } from "@/components/address-book-family-picker";
import { PasswordInput } from "@/components/password-input";
import { QuickAddSmartForm } from "@/components/quick-add-form";
import { WishlistItemSmartForm } from "@/components/wishlist-item-form";
import type { AppData } from "@/lib/types";

export function QuickAddForm() {
  return <QuickAddSmartForm action={quickAdd} />;
}

type QuickPreset = {
  kind: "task" | "shopping" | "note" | "event" | "meal" | "finance";
  title: string;
  details: string;
  category: string;
  priority: "laag" | "normaal" | "hoog";
  icon: ReactNode;
  pinned?: boolean;
};

const quickPresets: QuickPreset[] = [
  { kind: "task", title: "Afval buiten zetten", details: "Controleer welke bak aan straat moet.", category: "Huis", priority: "normaal", icon: <Trash2 size={16} /> },
  { kind: "shopping", title: "Melk", details: "1 pak", category: "Zuivel", priority: "normaal", icon: <ShoppingBasket size={16} /> },
  { kind: "event", title: "Tandartsafspraak plannen", details: "Locatie of notitie aanvullen", category: "Gezin", priority: "normaal", icon: <CalendarDays size={16} /> },
  { kind: "meal", title: "Pasta", details: "Pasta, saus, groente", category: "Avondeten", priority: "normaal", icon: <Utensils size={16} /> },
  { kind: "finance", title: "Schoolbetaling 12,50", details: "12,50", category: "Kinderen", priority: "normaal", icon: <Landmark size={16} /> },
  { kind: "note", title: "Oppasnotitie", details: "Belangrijke afspraak of instructie voor thuis.", category: "Gezin", priority: "normaal", pinned: true, icon: <MessageSquare size={16} /> },
];

export function QuickPresetGrid() {
  return (
    <section className="quick-presets card" aria-labelledby="quick-presets-title">
      <div className="section-head">
        <div>
          <span className="eyebrow">Veelgebruikt</span>
          <h2 id="quick-presets-title">Snelle presets</h2>
          <p className="muted">Gebruik als startpunt; je kunt de aangemaakte items daarna in de module aanpassen.</p>
        </div>
      </div>
      <div className="quick-preset-grid">
        {quickPresets.map((preset) => (
          <form action={quickAdd} className="quick-preset" key={`${preset.kind}-${preset.title}`}>
            <input type="hidden" name="kind" value={preset.kind} />
            <input type="hidden" name="title" value={preset.title} />
            <input type="hidden" name="details" value={preset.details} />
            <input type="hidden" name="category" value={preset.category} />
            <input type="hidden" name="priority" value={preset.priority} />
            {preset.pinned && <input type="hidden" name="pinned" value="on" />}
            <button type="submit">
              <span>{preset.icon}</span>
              <strong>{preset.title}</strong>
              <small>{preset.category}</small>
            </button>
          </form>
        ))}
      </div>
    </section>
  );
}

export function HouseholdDocumentForm() {
  return (
    <form className="card form" action={addHouseholdDocument}>
      <h2>Document toevoegen</h2>
      <div className="field">
        <label htmlFor="document-title">Titel</label>
        <input id="document-title" name="title" required />
      </div>
      <div className="field">
        <label htmlFor="document-category">Categorie</label>
        <select id="document-category" name="category" defaultValue="Algemeen">
          <option value="Algemeen">Algemeen</option>
          <option value="Identiteit">Identiteit</option>
          <option value="Verzekering">Verzekering</option>
          <option value="Garantie">Garantie</option>
          <option value="Contract">Contract</option>
          <option value="Medisch">Medisch</option>
          <option value="School">School</option>
          <option value="Huis">Huis</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="document-owner">Voor wie</label>
        <input id="document-owner" name="owner_name" placeholder="Gezinslid of huishouden" />
      </div>
      <div className="field">
        <label htmlFor="document-location">Bewaarplek</label>
        <input id="document-location" name="location" placeholder="Bijv. kluis, map, mail, cloud" />
      </div>
      <div className="field">
        <label htmlFor="document-reference">Referentie</label>
        <input id="document-reference" name="reference" placeholder="Polisnummer, factuurnummer, serienummer" />
      </div>
      <div className="field">
        <label htmlFor="document-expires">Vervalt op</label>
        <input id="document-expires" name="expires_at" type="date" />
      </div>
      <div className="field">
        <label htmlFor="document-notes">Notitie</label>
        <textarea id="document-notes" name="notes" rows={3} />
      </div>
      <label className="check-row">
        <input type="checkbox" name="is_sensitive" />
        Bevat gevoelige informatie
      </label>
      <button className="button primary">Document opslaan</button>
    </form>
  );
}

export function WishlistItemForm({ members = [] }: { members?: AppData["members"] }) {
  return <WishlistItemSmartForm action={addWishlistItem} members={members} />;
}

export function HouseholdNoteForm() {
  return (
    <form className="card form" action={addHouseholdNote}>
      <h2>Bericht plaatsen</h2>
      <div className="field">
        <label htmlFor="note-title">Titel</label>
        <input id="note-title" name="title" required />
      </div>
      <div className="field">
        <label htmlFor="note-body">Bericht</label>
        <textarea id="note-body" name="body" rows={5} required />
      </div>
      <div className="field">
        <label htmlFor="note-category">Categorie</label>
        <input id="note-category" name="category" defaultValue="Algemeen" />
      </div>
      <div className="field">
        <label htmlFor="note-expires">Zichtbaar tot</label>
        <input id="note-expires" name="expires_at" type="date" />
      </div>
      <label className="check-row">
        <input type="checkbox" name="pinned" />
        Vastzetten bovenaan
      </label>
      <button className="button primary">Bericht opslaan</button>
    </form>
  );
}

export function HouseholdContactForm() {
  return (
    <form className="card form" action={addHouseholdContact}>
      <h2>Contact toevoegen</h2>
      <div className="field">
        <label htmlFor="contact-name">Naam</label>
        <input id="contact-name" name="name" required />
      </div>
      <div className="field">
        <label htmlFor="contact-relationship">Rol</label>
        <input id="contact-relationship" name="relationship" placeholder="Huisarts, school, buren, oppas" />
      </div>
      <div className="field">
        <label htmlFor="contact-phone">Telefoon</label>
        <input id="contact-phone" name="phone" type="tel" />
      </div>
      <div className="field">
        <label htmlFor="contact-email">E-mail</label>
        <input id="contact-email" name="email" type="email" />
      </div>
      <div className="field">
        <label htmlFor="contact-address">Adres</label>
        <input id="contact-address" name="address" />
      </div>
      <div className="field">
        <label htmlFor="contact-priority">Prioriteit</label>
        <select id="contact-priority" name="priority" defaultValue="normaal">
          <option value="normaal">Normaal</option>
          <option value="belangrijk">Belangrijk</option>
          <option value="nood">Noodcontact</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="contact-notes">Notitie</label>
        <textarea id="contact-notes" name="notes" rows={3} />
      </div>
      <button className="button primary">Contact opslaan</button>
    </form>
  );
}

export function AddressBookContactForm() {
  return (
    <form className="card form" action={addAddressBookContact}>
      <h2>Contact toevoegen</h2>
      <div className="field">
        <label htmlFor="addressbook-contact-type">Type</label>
        <select id="addressbook-contact-type" name="contact_type" defaultValue="persoon">
          <option value="persoon">Persoon</option>
          <option value="gezin">Gezin of familie</option>
          <option value="organisatie">Organisatie</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="addressbook-contact-name">Naam</label>
        <input id="addressbook-contact-name" name="name" required placeholder="Bijv. Familie Jansen" />
      </div>
      <div className="field">
        <label htmlFor="addressbook-contact-relation">Relatie</label>
        <input id="addressbook-contact-relation" name="relationship" placeholder="Familie, buren, school, sportclub" />
      </div>
      <div className="quick-field-grid">
        <div className="field">
          <label htmlFor="addressbook-contact-phone">Telefoon</label>
          <input id="addressbook-contact-phone" name="phone" type="tel" />
        </div>
        <div className="field">
          <label htmlFor="addressbook-contact-email">E-mail</label>
          <input id="addressbook-contact-email" name="email" type="email" />
        </div>
      </div>
      <div className="field">
        <label htmlFor="addressbook-contact-address">Adres</label>
        <input id="addressbook-contact-address" name="address" placeholder="Straat en huisnummer" />
      </div>
      <div className="quick-field-grid">
        <div className="field">
          <label htmlFor="addressbook-contact-postal">Postcode</label>
          <input id="addressbook-contact-postal" name="postal_code" />
        </div>
        <div className="field">
          <label htmlFor="addressbook-contact-city">Plaats</label>
          <input id="addressbook-contact-city" name="city" />
        </div>
      </div>
      <div className="field">
        <label htmlFor="addressbook-contact-country">Land</label>
        <input id="addressbook-contact-country" name="country" defaultValue="Nederland" />
      </div>
      <div className="field">
        <label htmlFor="addressbook-contact-priority">Prioriteit</label>
        <select id="addressbook-contact-priority" name="priority" defaultValue="normaal">
          <option value="normaal">Normaal</option>
          <option value="belangrijk">Belangrijk</option>
          <option value="nood">Noodcontact</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="addressbook-contact-notes">Notitie</label>
        <textarea id="addressbook-contact-notes" name="notes" rows={3} />
      </div>
      <button className="button primary">Contact opslaan</button>
    </form>
  );
}

export function AddressBookMemberForm({ contacts }: { contacts: AppData["householdContacts"] }) {
  return (
    <form className="card form" action={addAddressBookMember}>
      <h2>Persoon toevoegen aan familie</h2>
      <div className="field">
        <label htmlFor="addressbook-member-family">Familie</label>
        <AddressBookFamilyPicker contacts={contacts.map((contact) => ({ id: contact.id, name: contact.name, relationship: contact.relationship }))} />
      </div>
      <div className="field">
        <label htmlFor="addressbook-member-name">Naam</label>
        <input id="addressbook-member-name" name="name" required />
      </div>
      <div className="quick-field-grid">
        <div className="field">
          <label htmlFor="addressbook-member-relation">Relatie</label>
          <input id="addressbook-member-relation" name="relationship" placeholder="Ouder, kind, opa" />
        </div>
        <div className="field">
          <label htmlFor="addressbook-member-birth">Geboortedatum</label>
          <input id="addressbook-member-birth" name="birth_date" type="date" />
        </div>
      </div>
      <div className="quick-field-grid">
        <div className="field">
          <label htmlFor="addressbook-member-phone">Telefoon</label>
          <input id="addressbook-member-phone" name="phone" type="tel" />
        </div>
        <div className="field">
          <label htmlFor="addressbook-member-email">E-mail</label>
          <input id="addressbook-member-email" name="email" type="email" />
        </div>
      </div>
      <div className="field">
        <label htmlFor="addressbook-member-notes">Notitie</label>
        <textarea id="addressbook-member-notes" name="notes" rows={2} />
      </div>
      <p className="muted">Een geboortedatum wordt automatisch opgenomen in de verjaardagskalender.</p>
      <button className="button primary">Persoon opslaan</button>
    </form>
  );
}

export function AddressBookImportForm() {
  return (
    <form className="card form" action={importAddressBookContacts}>
      <h2>Contacten importeren</h2>
      <div className="field">
        <label htmlFor="addressbook-import-file">Bestand</label>
        <input id="addressbook-import-file" name="contacts_file" type="file" accept=".vcf,.csv,text/vcard,text/x-vcard,text/csv" required />
      </div>
      <p className="muted">Importeer vCard (.vcf) of CSV. Naam, telefoon, e-mail, adres en geboortedatum worden herkend.</p>
      <button className="button primary">Importeren</button>
    </form>
  );
}

export function BirthdayForm({ members }: { members: AppData["members"] }) {
  return (
    <form className="card form" action={addHouseholdBirthday}>
      <h2>Verjaardag toevoegen</h2>
      <div className="field">
        <label htmlFor="birthday-name">Naam</label>
        <input id="birthday-name" name="name" required />
      </div>
      <div className="field">
        <label htmlFor="birthday-date">Geboortedatum</label>
        <input id="birthday-date" name="birth_date" type="date" required />
      </div>
      <div className="field">
        <label htmlFor="birthday-member">Gezinslid</label>
        <select id="birthday-member" name="member_id" defaultValue="">
          <option value="">Niet gekoppeld</option>
          {members.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.profile?.full_name ?? member.profile?.email ?? "Gezinslid"}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="birthday-relation">Relatie</label>
        <input id="birthday-relation" name="relation" placeholder="Bijv. oma, vriend of gezin" />
      </div>
      <div className="field">
        <label htmlFor="birthday-notes">Notitie</label>
        <input id="birthday-notes" name="notes" placeholder="Optioneel" />
      </div>
      <button className="button primary">Verjaardag opslaan</button>
    </form>
  );
}

export function HouseholdInfoForm() {
  return (
    <form className="card form" action={addHouseholdInfoItem}>
      <h2>Huisinfo toevoegen</h2>
      <div className="field">
        <label htmlFor="info-title">Titel</label>
        <input id="info-title" name="title" required />
      </div>
      <div className="field">
        <label htmlFor="info-category">Categorie</label>
        <input id="info-category" name="category" placeholder="Huis, techniek, verzekering, school" defaultValue="Huis" />
      </div>
      <div className="field">
        <label htmlFor="info-value">Waarde</label>
        <input id="info-value" name="value" placeholder="Bijv. locatie, polisnummer of korte instructie" />
      </div>
      <div className="field">
        <label htmlFor="info-notes">Notitie</label>
        <textarea id="info-notes" name="notes" rows={3} />
      </div>
      <label className="check-row">
        <input type="checkbox" name="is_sensitive" />
        Bevat gevoelige informatie
      </label>
      <button className="button primary">Info opslaan</button>
    </form>
  );
}

export function TaskForm({ members }: { members: AppData["members"] }) {
  return (
    <form className="card form" action={addTask}>
      <h2>Taak toevoegen</h2>
      <div className="field">
        <label htmlFor="task-title">Titel</label>
        <input id="task-title" name="title" required />
      </div>
      <div className="field">
        <label htmlFor="task-description">Notitie</label>
        <textarea id="task-description" name="description" rows={3} placeholder="Optioneel, bijv. waar ligt iets of waar moet op gelet worden" />
      </div>
      <div className="field">
        <label htmlFor="task-assignee">Toewijzen</label>
        <select id="task-assignee" name="assignee_id" defaultValue="">
          <option value="">Niet toegewezen</option>
          {members.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.profile?.full_name ?? member.profile?.email ?? "Gezinslid"}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="task-priority">Prioriteit</label>
        <select id="task-priority" name="priority" defaultValue="normaal">
          <option value="laag">Laag</option>
          <option value="normaal">Normaal</option>
          <option value="hoog">Hoog</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="task-due">Deadline</label>
        <input id="task-due" name="due_date" type="date" />
      </div>
      <div className="field">
        <label htmlFor="task-recurrence">Herhaling</label>
        <select id="task-recurrence" name="recurrence" defaultValue="none">
          <option value="none">Eenmalig</option>
          <option value="daily">Dagelijks</option>
          <option value="weekly">Wekelijks</option>
          <option value="monthly">Maandelijks</option>
        </select>
      </div>
      <button className="button primary">Toevoegen</button>
    </form>
  );
}

export function ShoppingForm({ listId, defaultStore }: { listId: string | null; defaultStore?: string | null }) {
  return (
    <form className="card form" action={addShoppingItem}>
      <h2>Boodschap toevoegen</h2>
      <input type="hidden" name="list_id" value={listId ?? ""} />
      <div className="field">
        <label htmlFor="shop-name">Naam</label>
        <input id="shop-name" name="name" required />
      </div>
      <div className="field">
        <label htmlFor="shop-qty">Aantal</label>
        <input id="shop-qty" name="quantity" placeholder="bijv. 2 pakken" />
      </div>
      <div className="field">
        <label htmlFor="shop-cat">Categorie</label>
        <input id="shop-cat" name="category" placeholder="Groente, zuivel, drogist" />
      </div>
      <div className="field">
        <label htmlFor="shop-recurrence">Herhaling</label>
        <select id="shop-recurrence" name="recurrence" defaultValue="none">
          <option value="none">Niet terugkerend</option>
          <option value="weekly">Wekelijks</option>
          <option value="biweekly">Elke twee weken</option>
          <option value="monthly">Maandelijks</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="shop-price">Prijs</label>
        <input id="shop-price" name="price" type="number" min="0" step="0.01" placeholder="Optioneel" />
      </div>
      <div className="field">
        <label htmlFor="shop-store">Winkel</label>
        <input id="shop-store" name="store" defaultValue={defaultStore ?? ""} placeholder="bijv. Albert Heijn" />
      </div>
      <button className="button primary">Toevoegen</button>
    </form>
  );
}

export function MealPlanForm() {
  return (
    <form className="card form" action={addMealPlan}>
      <h2>Maaltijd plannen</h2>
      <div className="field">
        <label htmlFor="meal-title">Gerecht</label>
        <input id="meal-title" name="title" required />
      </div>
      <div className="field">
        <label htmlFor="meal-date">Datum</label>
        <input id="meal-date" name="planned_date" type="date" required />
      </div>
      <div className="field">
        <label htmlFor="meal-type">Moment</label>
        <select id="meal-type" name="meal_type" defaultValue="avondeten">
          <option value="ontbijt">Ontbijt</option>
          <option value="lunch">Lunch</option>
          <option value="avondeten">Avondeten</option>
          <option value="snack">Snack</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="meal-ingredients">Ingrediënten</label>
        <textarea id="meal-ingredients" name="ingredients" rows={5} placeholder="Een ingrediënt per regel, of gescheiden met komma's" />
      </div>
      <div className="field">
        <label htmlFor="meal-notes">Notitie</label>
        <textarea id="meal-notes" name="notes" rows={3} placeholder="Bijv. wie kookt, restjes, voorbereiding" />
      </div>
      <button className="button primary">Maaltijd opslaan</button>
    </form>
  );
}

export function MaintenanceForm() {
  return (
    <form className="card form" action={addMaintenanceItem}>
      <h2>Onderhoud toevoegen</h2>
      <div className="field">
        <label htmlFor="maintenance-title">Titel</label>
        <input id="maintenance-title" name="title" placeholder="Bijv. rookmelders testen" required />
      </div>
      <div className="field">
        <label htmlFor="maintenance-area">Onderdeel</label>
        <input id="maintenance-area" name="area" placeholder="Veiligheid, tuin, techniek, auto" />
      </div>
      <div className="field">
        <label htmlFor="maintenance-provider">Leverancier/contact</label>
        <input id="maintenance-provider" name="provider" placeholder="Installateur, verzekering, gemeente" />
      </div>
      <div className="field">
        <label htmlFor="maintenance-due">Vervaldatum</label>
        <input id="maintenance-due" name="due_date" type="date" />
      </div>
      <div className="field">
        <label htmlFor="maintenance-frequency">Herhaling</label>
        <select id="maintenance-frequency" name="frequency" defaultValue="none">
          <option value="none">Eenmalig</option>
          <option value="monthly">Maandelijks</option>
          <option value="quarterly">Elk kwartaal</option>
          <option value="yearly">Jaarlijks</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="maintenance-notes">Notitie</label>
        <textarea id="maintenance-notes" name="notes" rows={3} placeholder="Wat moet er gebeuren, waar ligt documentatie, wat kost het?" />
      </div>
      <button className="button primary">Onderhoud opslaan</button>
    </form>
  );
}

export function FinanceForm() {
  return (
    <form className="card form" action={addFinanceItem}>
      <h2>Gelditem toevoegen</h2>
      <div className="field">
        <label htmlFor="finance-title">Titel</label>
        <input id="finance-title" name="title" required />
      </div>
      <div className="field">
        <label htmlFor="finance-amount">Bedrag</label>
        <input id="finance-amount" name="amount" type="number" min="0" step="0.01" required />
      </div>
      <div className="field">
        <label htmlFor="finance-category">Categorie</label>
        <select id="finance-category" name="category" defaultValue="Vaste lasten">
          <option value="Vaste lasten">Vaste lasten</option>
          <option value="Wonen">Wonen</option>
          <option value="Energie">Energie</option>
          <option value="Verzekering">Verzekering</option>
          <option value="Abonnementen">Abonnementen</option>
          <option value="Boodschappen">Boodschappen</option>
          <option value="Vervoer">Vervoer</option>
          <option value="Kinderen">Kinderen</option>
          <option value="Sparen">Sparen</option>
          <option value="Overig">Overig</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="finance-frequency">Frequentie</label>
        <select id="finance-frequency" name="frequency" defaultValue="maandelijks">
          <option value="eenmalig">Eenmalig</option>
          <option value="maandelijks">Maandelijks</option>
          <option value="jaarlijks">Jaarlijks</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="finance-due">Betaaldatum</label>
        <input id="finance-due" name="due_date" type="date" />
      </div>
      <button className="button primary">Toevoegen</button>
    </form>
  );
}

export function FinanceBudgetForm() {
  return (
    <form className="card form" action={addFinanceBudget}>
      <h2>Budget toevoegen</h2>
      <div className="field">
        <label htmlFor="budget-category">Categorie</label>
        <input id="budget-category" name="category" placeholder="Bijv. boodschappen, wonen, abonnementen" required />
      </div>
      <div className="field">
        <label htmlFor="budget-limit">Maandlimiet</label>
        <input id="budget-limit" name="monthly_limit" type="number" min="0" step="0.01" required />
      </div>
      <div className="field">
        <label htmlFor="budget-threshold">Waarschuwing vanaf</label>
        <select id="budget-threshold" name="alert_threshold" defaultValue="80">
          <option value="70">70%</option>
          <option value="80">80%</option>
          <option value="90">90%</option>
          <option value="100">100%</option>
        </select>
      </div>
      <button className="button primary">Budget opslaan</button>
    </form>
  );
}

export function CalendarForm({ members }: { members: AppData["members"] }) {
  return (
    <form className="card form" action={addCalendarEvent}>
      <h2>Afspraak toevoegen</h2>
      <div className="field">
        <label htmlFor="event-title">Titel</label>
        <input id="event-title" name="title" required />
      </div>
      <div className="field">
        <label htmlFor="event-start">Start</label>
        <input id="event-start" name="starts_at" type="datetime-local" required />
      </div>
      <div className="field">
        <label htmlFor="event-location">Locatie</label>
        <input id="event-location" name="location" />
      </div>
      <div className="field">
        <label htmlFor="event-members">Gezinsleden</label>
        <select id="event-members" name="participant_ids" multiple>
          {members.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.profile?.full_name ?? member.profile?.email ?? "Gezinslid"}
            </option>
          ))}
        </select>
      </div>
      <button className="button primary">Toevoegen</button>
    </form>
  );
}

export function HomeAssistantForm() {
  return (
    <form className="card form" action={saveHomeAssistantConfig}>
      <h2>Home Assistant koppelen</h2>
      <div className="field">
        <label htmlFor="ha-url">Home Assistant URL</label>
        <input id="ha-url" name="base_url" placeholder="https://homeassistant.local:8123" required />
      </div>
      <div className="field">
        <label htmlFor="ha-token">Long-lived access token</label>
        <PasswordInput id="ha-token" name="token" required autoComplete="off" />
      </div>
      <button className="button primary">Opslaan</button>
    </form>
  );
}

export function HueConfigForm() {
  return (
    <form className="card form" action={saveHueConfig}>
      <h2>Philips Hue koppelen</h2>
      <div className="field">
        <label htmlFor="hue-bridge-url">Bridge URL</label>
        <input id="hue-bridge-url" name="bridge_url" placeholder="https://192.168.1.10" required />
      </div>
      <div className="field">
        <label htmlFor="hue-app-key">Hue app key</label>
        <PasswordInput id="hue-app-key" name="app_key" required autoComplete="off" />
      </div>
      <p className="muted">
        Maak een app key aan door de Hue Bridge link-knop te gebruiken en daarna via de Hue API een user/app key te registreren.
      </p>
      <button className="button primary">Hue opslaan</button>
    </form>
  );
}

export function GoogleHomeForm() {
  return (
    <form className="card form" action={saveGoogleHomeIntegration}>
      <h2>Google Home koppelen</h2>
      <div className="field">
        <label htmlFor="google-home-mode">Modus</label>
        <select id="google-home-mode" name="mode" defaultValue="nest_sdm">
          <option value="nest_sdm">Nest SDM</option>
          <option value="home_apis">Google Home APIs</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="google-project-id">Device Access project ID</label>
        <input id="google-project-id" name="project_id" placeholder="UUID uit Google Device Access Console" />
      </div>
      <div className="field">
        <label htmlFor="google-client-id">OAuth client ID</label>
        <input id="google-client-id" name="client_id" />
      </div>
      <div className="field">
        <label htmlFor="google-client-secret">OAuth client secret</label>
        <PasswordInput id="google-client-secret" name="client_secret" autoComplete="off" />
      </div>
      <p className="muted">
        Voeg in Google Cloud deze redirect URI toe: `/api/google-home/oauth/callback` op je app-domein. Nest SDM synchroniseert
        ondersteunde Nest-apparaten; Google Home APIs blijven voorbereid voor een latere mobiele platformlaag.
      </p>
      <button className="button primary">Google opslaan</button>
    </form>
  );
}

export function OutlookCalendarForm() {
  return (
    <form className="card form" action={saveOutlookOAuthConfig}>
      <h2>Outlook agenda koppelen</h2>
      <div className="field">
        <label htmlFor="outlook-client-id">Application (client) ID</label>
        <input id="outlook-client-id" name="client_id" required autoComplete="off" />
      </div>
      <div className="field">
        <label htmlFor="outlook-client-secret">Client secret value</label>
        <PasswordInput id="outlook-client-secret" name="client_secret" required autoComplete="new-password" />
      </div>
      <div className="field">
        <label htmlFor="outlook-tenant-id">Accounttype</label>
        <select id="outlook-tenant-id" name="tenant_id" defaultValue="consumers">
          <option value="consumers">Alleen persoonlijke Outlook.com-accounts</option>
          <option value="common">Werk-, school- en persoonlijke accounts</option>
        </select>
      </div>
      <p className="muted">
        Gebruik de secret <strong>Value</strong> uit Microsoft Entra, niet de Secret ID. Deze waarde wordt server-side opgeslagen en niet opnieuw getoond.
      </p>
      <button className="button">Outlook-configuratie opslaan</button>
      <p className="muted">Daarna meld je ieder gezinslid aan met het Outlook-account waarvan de agenda getoond moet worden.</p>
      <a className="button primary" href="/api/outlook-calendar/oauth/start">Aanmelden met Outlook</a>
    </form>
  );
}

export function IcsCalendarSubscriptionForm() {
  return (
    <form className="card form" action={saveIcsCalendarSubscription}>
      <h2>ICS agenda toevoegen</h2>
      <div className="field">
        <label htmlFor="ics-display-name">Naam</label>
        <input id="ics-display-name" name="display_name" defaultValue="Gedeelde agenda" required />
      </div>
      <div className="field">
        <label htmlFor="ics-feed-url">ICS-abonnementslink</label>
        <input id="ics-feed-url" name="feed_url" type="url" placeholder="https://.../calendar.ics" required />
      </div>
      <p className="muted">De link wordt alleen server-side opgeslagen. Synchroniseer daarna om afspraken op te halen.</p>
      <button className="button primary">Agenda toevoegen</button>
    </form>
  );
}

export function IcsCalendarFileImportForm() {
  return (
    <form className="card form" action={importIcsCalendarFile}>
      <h2>ICS-bestand importeren</h2>
      <div className="field">
        <label htmlFor="ics-file-display-name">Naam</label>
        <input id="ics-file-display-name" name="display_name" defaultValue="Geimporteerde agenda" required />
      </div>
      <div className="field">
        <label htmlFor="ics-file">ICS-bestand</label>
        <input id="ics-file" name="ics_file" type="file" accept=".ics,text/calendar" required />
      </div>
      <p className="muted">Eenmalige import tot 2 MB. Upload later een nieuw bestand met dezelfde agendanaam om deze agenda bij te werken.</p>
      <button className="button primary">Bestand importeren</button>
    </form>
  );
}

export function BunqConnectionForm() {
  return (
    <form className="card form" action={saveBunqConnection}>
      <h2>bunq koppelen</h2>
      <div className="field">
        <label htmlFor="bunq-environment">Omgeving</label>
        <select id="bunq-environment" name="environment" defaultValue="sandbox">
          <option value="sandbox">Sandbox</option>
          <option value="production">Productie</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="bunq-api-key">API key</label>
        <PasswordInput id="bunq-api-key" name="api_key" placeholder="Optionele fallback API key" autoComplete="off" />
      </div>
      <div className="field">
        <label htmlFor="bunq-oauth-client-id">OAuth client ID</label>
        <input id="bunq-oauth-client-id" name="oauth_client_id" placeholder="Uit bunq Developer" />
      </div>
      <div className="field">
        <label htmlFor="bunq-oauth-client-secret">OAuth client secret</label>
        <PasswordInput id="bunq-oauth-client-secret" name="oauth_client_secret" placeholder="Uit bunq Developer" autoComplete="off" />
      </div>
      <p className="muted">
        OAuth is de voorkeursroute. De API key blijft alleen als developer fallback bestaan. Secrets worden server-side opgeslagen.
      </p>
      <BunqSubmitButton />
    </form>
  );
}

export function AbnAmroStatementUploadForm() {
  return (
    <form className="card form" action={importAbnAmroStatement}>
      <h2>ABN AMRO afschrift importeren</h2>
      <div className="field">
        <label htmlFor="abn-account-name">Naam rekening</label>
        <input id="abn-account-name" name="account_name" placeholder="Bijvoorbeeld ABN priverekening" />
      </div>
      <div className="field">
        <label htmlFor="abn-statement-file">Afschriftbestand</label>
        <input
          id="abn-statement-file"
          name="statement_file"
          type="file"
          accept=".xls,.xlsx,.csv,.txt,.tsv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,text/plain"
          required
        />
      </div>
      <p className="muted">
        Upload je ABN AMRO afschrift als Excel of CSV. De import voegt transacties idempotent toe en bewaart het bestand zelf niet.
      </p>
      <button className="button primary">Afschrift importeren</button>
    </form>
  );
}

export function TaskIntegrationForm() {
  return (
    <form className="card form" action={saveTaskIntegration}>
      <h2>Takenkoppeling</h2>
      <div className="field">
        <label htmlFor="task-provider">Provider</label>
        <select id="task-provider" name="provider" defaultValue="microsoft_todo">
          <option value="microsoft_todo">Microsoft To Do</option>
          <option value="apple_reminders">Apple Herinneringen</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="task-sync-direction">Synchronisatie</label>
        <select id="task-sync-direction" name="sync_direction" defaultValue="two_way">
          <option value="two_way">Twee richtingen</option>
          <option value="import_only">Alleen importeren</option>
          <option value="export_only">Alleen exporteren</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="task-client-id">Microsoft client ID</label>
        <input id="task-client-id" name="client_id" placeholder="Alleen nodig voor Microsoft To Do OAuth" />
      </div>
      <div className="field">
        <label htmlFor="task-tenant-id">Microsoft tenant ID</label>
        <input id="task-tenant-id" name="tenant_id" placeholder="common, consumers of tenant-id" />
      </div>
      <p className="muted">
        Microsoft To Do gebruikt Microsoft Graph OAuth. Apple Herinneringen vereist later een native macOS/iOS bridge via EventKit.
      </p>
      <button className="button primary">Koppeling opslaan</button>
    </form>
  );
}
