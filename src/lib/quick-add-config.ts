export type QuickAddKind = "task" | "shopping" | "note" | "event" | "meal" | "finance";

export type QuickAddKindConfig = {
  value: QuickAddKind;
  label: string;
  detail: string;
  titleLabel: string;
  titlePlaceholder: string;
  detailsLabel: string;
  detailsPlaceholder: string;
  categoryLabel: string;
  categoryPlaceholder: string;
  dateLabel: string | null;
  showPriority: boolean;
  showPinned: boolean;
  showExpires: boolean;
  submitLabel: string;
  help: string;
};

export const quickAddKindConfigs: QuickAddKindConfig[] = [
  {
    value: "task",
    label: "Taak",
    detail: "Actie of reminder",
    titleLabel: "Wat moet er gebeuren?",
    titlePlaceholder: "Bijv. vuilnis buiten zetten",
    detailsLabel: "Beschrijving",
    detailsPlaceholder: "Extra context, afspraak of stappen",
    categoryLabel: "Categorie",
    categoryPlaceholder: "Bijv. Huis, School, Administratie",
    dateLabel: "Deadline",
    showPriority: true,
    showPinned: false,
    showExpires: false,
    submitLabel: "Taak toevoegen",
    help: "Komt in Taken. Gebruik datum en prioriteit voor focus op Vandaag en Week.",
  },
  {
    value: "shopping",
    label: "Boodschap",
    detail: "Op de gedeelde lijst",
    titleLabel: "Wat moet op de lijst?",
    titlePlaceholder: "Bijv. melk",
    detailsLabel: "Hoeveelheid",
    detailsPlaceholder: "Bijv. 1 pak, 500 gram, voor 3 dagen",
    categoryLabel: "Schap of categorie",
    categoryPlaceholder: "Bijv. Zuivel, Groente, Huishouden",
    dateLabel: null,
    showPriority: false,
    showPinned: false,
    showExpires: false,
    submitLabel: "Boodschap toevoegen",
    help: "Komt direct op de gedeelde boodschappenlijst en wordt als product onthouden.",
  },
  {
    value: "note",
    label: "Prikbord",
    detail: "Bericht voor thuis",
    titleLabel: "Titel van het bericht",
    titlePlaceholder: "Bijv. Oppas komt vrijdag",
    detailsLabel: "Bericht",
    detailsPlaceholder: "Wat moet iedereen weten?",
    categoryLabel: "Categorie",
    categoryPlaceholder: "Bijv. Gezin, School, Huis",
    dateLabel: null,
    showPriority: false,
    showPinned: true,
    showExpires: true,
    submitLabel: "Bericht plaatsen",
    help: "Komt op het Prikbord. Gebruik vastzetten voor belangrijke gezinsberichten.",
  },
  {
    value: "event",
    label: "Afspraak",
    detail: "In de gezinsagenda",
    titleLabel: "Welke afspraak?",
    titlePlaceholder: "Bijv. Tandarts",
    detailsLabel: "Locatie of notitie",
    detailsPlaceholder: "Bijv. Praktijk Centrum, neem pasje mee",
    categoryLabel: "Categorie",
    categoryPlaceholder: "Bijv. Zorg, School, Sport",
    dateLabel: "Datum",
    showPriority: false,
    showPinned: false,
    showExpires: false,
    submitLabel: "Afspraak toevoegen",
    help: "Komt in de gezinsagenda. De app plant de afspraak standaard om 09:00 op de gekozen dag.",
  },
  {
    value: "meal",
    label: "Maaltijd",
    detail: "Voor de eetplanning",
    titleLabel: "Wat eten jullie?",
    titlePlaceholder: "Bijv. Pasta pesto",
    detailsLabel: "Ingredienten",
    detailsPlaceholder: "Bijv. Pasta, pesto, tomaat, rucola",
    categoryLabel: "Maaltijdtype",
    categoryPlaceholder: "Bijv. Avondeten, lunch",
    dateLabel: "Datum",
    showPriority: false,
    showPinned: false,
    showExpires: false,
    submitLabel: "Maaltijd plannen",
    help: "Komt in Maaltijden en helpt later richting boodschappen en weekplanning.",
  },
  {
    value: "finance",
    label: "Geld",
    detail: "Betaalmoment",
    titleLabel: "Wat moet betaald of onthouden worden?",
    titlePlaceholder: "Bijv. Schoolfoto 12,50",
    detailsLabel: "Bedrag of notitie",
    detailsPlaceholder: "Zet een bedrag in titel of details, bijvoorbeeld 12,50",
    categoryLabel: "Categorie",
    categoryPlaceholder: "Bijv. Kinderen, Huis, Abonnement",
    dateLabel: "Betaaldatum",
    showPriority: false,
    showPinned: false,
    showExpires: false,
    submitLabel: "Betaalmoment toevoegen",
    help: "Komt in Geld als eenmalig betaalmoment. Een bedrag is verplicht.",
  },
];

export function getQuickAddKindConfig(kind: string | null | undefined) {
  return quickAddKindConfigs.find((item) => item.value === kind) ?? quickAddKindConfigs[0];
}
