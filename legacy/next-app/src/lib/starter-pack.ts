export type StarterPack = ReturnType<typeof buildStarterPack>;
export type StarterPackSummary = ReturnType<typeof buildStarterPackSummary>;

export function buildStarterPack(today = new Date().toISOString().slice(0, 10)) {
  return {
    contacts: [
      { name: "Huisarts", relationship: "Zorg", priority: "belangrijk", notes: "Vul telefoonnummer en adres aan." },
      { name: "School of opvang", relationship: "Kinderen", priority: "belangrijk", notes: "Vul de belangrijkste contactpersoon aan." },
      { name: "Noodcontact familie", relationship: "Familie", priority: "nood", notes: "Vul telefoonnummer in voor noodgevallen." },
    ],
    householdInfoItems: [
      { title: "Meterkast", category: "Huis", value: "Vul locatie en hoofdschakelaars aan.", notes: "Handig voor storingen en oppas." },
      { title: "Wifi", category: "Techniek", value: "Vul netwerknaam en veilige bewaarplek voor wachtwoord aan.", notes: "Sla het echte wachtwoord alleen op als je dat bewust wilt." },
      { title: "Huisverzekering", category: "Verzekering", value: "Vul verzekeraar en polislocatie aan.", notes: "Koppel later het document in Documenten." },
    ],
    tasks: [
      { title: "Afval controleren", description: "Controleer welke bak aan straat moet.", priority: "normaal", due_date: addDays(today, 1), recurrence: "weekly" },
      { title: "Weekplanning doornemen", description: "Bekijk agenda, taken, maaltijden en boodschappen voor komende week.", priority: "hoog", due_date: nextMonday(today), recurrence: "weekly" },
      { title: "Administratie bijwerken", description: "Facturen, abonnementen en gezinsdocumenten nalopen.", priority: "normaal", due_date: addDays(today, 7), recurrence: "monthly" },
    ],
    shoppingProducts: [
      { name: "Melk", category: "Zuivel", default_quantity: "1 pak", recurrence: "weekly" },
      { name: "Brood", category: "Bakkerij", default_quantity: "1 brood", recurrence: "weekly" },
      { name: "Fruit", category: "Groente & fruit", default_quantity: "voor 3 dagen", recurrence: "weekly" },
      { name: "Koffie", category: "Voorraad", default_quantity: "1 pak", recurrence: "monthly" },
      { name: "WC-papier", category: "Huishouden", default_quantity: "1 pak", recurrence: "monthly" },
    ],
    financeBudgets: [
      { category: "Boodschappen", monthly_limit_cents: 60000, alert_threshold: 0.8 },
      { category: "Huis", monthly_limit_cents: 150000, alert_threshold: 0.8 },
      { category: "Kinderen", monthly_limit_cents: 25000, alert_threshold: 0.85 },
      { category: "Vrije tijd", monthly_limit_cents: 30000, alert_threshold: 0.8 },
    ],
    financeItems: [
      { title: "Huur of hypotheek", category: "Huis", amount_cents: 0, frequency: "maandelijks", due_date: firstDayNextMonth(today), status: "gepland" },
      { title: "Energie", category: "Huis", amount_cents: 0, frequency: "maandelijks", due_date: addDays(today, 10), status: "gepland" },
      { title: "Internet en mobiel", category: "Abonnementen", amount_cents: 0, frequency: "maandelijks", due_date: addDays(today, 14), status: "gepland" },
    ],
    maintenanceItems: [
      { title: "Rookmelders testen", area: "Veiligheid", provider: null, due_date: addDays(today, 14), frequency: "monthly", notes: "Test alle melders en vervang batterijen waar nodig." },
      { title: "CV of warmtepomp check", area: "Techniek", provider: null, due_date: addDays(today, 30), frequency: "yearly", notes: "Vul onderhoudspartij en laatste onderhoudsdatum aan." },
    ],
    documents: [
      { title: "Paspoorten en ID-kaarten", category: "Identiteit", location: "Vul bewaarplek aan", notes: "Zet vervaldatums erbij voor reminders." },
      { title: "Verzekeringspolissen", category: "Verzekering", location: "Vul map of cloudlocatie aan", notes: "Bundel huis, zorg, auto en aansprakelijkheid." },
      { title: "Garanties en grote aankopen", category: "Garantie", location: "Vul map of mailzoekterm aan", notes: "Handig voor apparaten en reparaties." },
    ],
    notes: [
      { title: "Gezinsapp gestart", body: "Vul deze week de belangrijkste contacten, taken, boodschappen en vaste lasten aan.", category: "Start", pinned: true, expires_at: addDays(today, 14) },
    ],
    mealPlans: [
      { planned_date: today, meal_type: "avondeten", title: "Weekmenu invullen", notes: "Vervang dit door het echte eten van vandaag.", ingredients: "Groente, basisvoorraad" },
    ],
  } as const;
}

export function buildStarterPackSummary(pack: StarterPack = buildStarterPack()) {
  const modules = [
    { id: "contacts", label: "Contacten", count: pack.contacts.length, href: "/gezin" },
    { id: "house", label: "Huisinfo", count: pack.householdInfoItems.length, href: "/gezin" },
    { id: "tasks", label: "Taken", count: pack.tasks.length, href: "/taken" },
    { id: "shopping", label: "Boodschappen", count: pack.shoppingProducts.length, href: "/boodschappen" },
    { id: "finance", label: "Geld", count: pack.financeBudgets.length + pack.financeItems.length, href: "/geld" },
    { id: "maintenance", label: "Onderhoud", count: pack.maintenanceItems.length, href: "/onderhoud" },
    { id: "documents", label: "Documenten", count: pack.documents.length, href: "/documenten" },
    { id: "notes", label: "Prikbord", count: pack.notes.length, href: "/prikbord" },
    { id: "meals", label: "Maaltijden", count: pack.mealPlans.length, href: "/boodschappen?tab=maaltijden" },
  ];
  const totalItems = modules.reduce((sum, module) => sum + module.count, 0);

  return {
    totalItems,
    modules,
    nextEdits: [
      { title: "Bedragen invullen", detail: "Vervang nulbedragen door echte vaste lasten en budgetten.", href: "/geld" },
      { title: "Telefoons en adressen aanvullen", detail: "Maak contacten en noodkaart bruikbaar voor oppas en gezinsleden.", href: "/gezin" },
      { title: "Bewaarplekken controleren", detail: "Zet echte documentlocaties en vervaldatums bij belangrijke stukken.", href: "/documenten" },
    ],
  };
}

function addDays(date: string, days: number) {
  const value = new Date(`${date}T12:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function nextMonday(date: string) {
  const value = new Date(`${date}T12:00:00.000Z`);
  const day = value.getUTCDay();
  const daysUntilMonday = day === 1 ? 7 : (8 - day) % 7 || 1;
  return addDays(date, daysUntilMonday);
}

function firstDayNextMonth(date: string) {
  const value = new Date(`${date}T12:00:00.000Z`);
  value.setUTCMonth(value.getUTCMonth() + 1, 1);
  return value.toISOString().slice(0, 10);
}
