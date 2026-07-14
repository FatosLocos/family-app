import type { AppData } from "@/lib/types";

export type SetupStep = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
  group: "Basis" | "Dagelijks" | "Planning" | "Huis" | "Koppelingen";
  priority?: "hoog" | "normaal";
};

export type SetupGroupProgress = {
  group: SetupStep["group"];
  done: number;
  total: number;
  percent: number;
};

export type SetupOverview = {
  steps: SetupStep[];
  progress: ReturnType<typeof setupProgress>;
  grouped: Record<SetupStep["group"], SetupStep[]>;
  groupProgress: SetupGroupProgress[];
  nextSteps: SetupStep[];
  highImpactOpen: SetupStep[];
  weakestGroup: SetupGroupProgress | null;
  nextAction: SetupStep | null;
};

export function buildSetupSteps(data: AppData): SetupStep[] {
  return [
    {
      id: "members",
      title: "Gezinsleden toegevoegd",
      detail: data.members.length > 1 ? `${data.members.length} gezinsleden actief` : "Nodig gezinsleden uit voor eigen accounts.",
      href: "/instellingen",
      done: data.members.length > 1,
      group: "Basis",
      priority: "hoog",
    },
    {
      id: "profile",
      title: "Profielen herkenbaar",
      detail: "Namen, telefoons en kleuren maken taken en noodinfo duidelijker.",
      href: "/instellingen",
      done: data.members.every((member) => Boolean(member.profile?.full_name || member.profile?.email)),
      group: "Basis",
      priority: "hoog",
    },
    {
      id: "contacts",
      title: "Belangrijke contacten",
      detail: "Huisarts, school, opvang, buren of oppas staan klaar.",
      href: "/gezin",
      done: data.householdContacts.length >= 3,
      group: "Basis",
      priority: "hoog",
    },
    {
      id: "tasks",
      title: "Taken ingericht",
      detail: "Gebruik taken voor vaste routines en losse acties.",
      href: "/taken",
      done: data.tasks.length > 0,
      group: "Dagelijks",
      priority: "hoog",
    },
    {
      id: "shopping",
      title: "Boodschappenlijst actief",
      detail: "Zet terugkerende producten en veelgekochte items klaar.",
      href: "/boodschappen",
      done: data.shoppingItems.length > 0 || data.shoppingProducts.length > 0,
      group: "Dagelijks",
      priority: "hoog",
    },
    {
      id: "meals",
      title: "Maaltijdplanning gestart",
      detail: "Plan eten vooruit en stuur ingredienten naar boodschappen.",
      href: "/boodschappen?tab=maaltijden",
      done: data.mealPlans.length > 0,
      group: "Dagelijks",
      priority: "normaal",
    },
    {
      id: "routines",
      title: "Routines actief",
      detail: "Terugkerende taken, boodschappen of onderhoud nemen vaste patronen over.",
      href: "/routines",
      done:
        data.tasks.some((task) => task.recurrence && task.recurrence !== "none") ||
        data.shoppingProducts.some((product) => product.recurrence !== "none") ||
        data.maintenanceItems.some((item) => item.frequency !== "none"),
      group: "Dagelijks",
      priority: "normaal",
    },
    {
      id: "calendar",
      title: "Gezinsagenda gekoppeld",
      detail: "Outlook-agenda's of handmatige afspraken vullen Vandaag en Week.",
      href: "/agenda",
      done: data.calendarIntegrations.some((item) => item.status === "configured") || data.calendarEvents.length > 0,
      group: "Planning",
      priority: "hoog",
    },
    {
      id: "finance",
      title: "Geld overzichtelijk",
      detail: "Vaste lasten, abonnementen en budgetten geven grip.",
      href: "/geld",
      done: data.financeItems.length > 0 && data.financeBudgets.length > 0,
      group: "Planning",
      priority: "hoog",
    },
    {
      id: "documents",
      title: "Documenten vindbaar",
      detail: "Polissen, garanties, contracten en referenties staan bij elkaar.",
      href: "/documenten",
      done: data.householdDocuments.length >= 3,
      group: "Huis",
      priority: "normaal",
    },
    {
      id: "house-info",
      title: "Huisinformatie gevuld",
      detail: "Meterkast, verzekeringen, leveranciers en instructies zijn vindbaar.",
      href: "/gezin",
      done: data.householdInfoItems.length >= 3,
      group: "Huis",
      priority: "normaal",
    },
    {
      id: "maintenance",
      title: "Onderhoud gepland",
      detail: "Terugkerende controles voor huis en apparaten staan klaar.",
      href: "/onderhoud",
      done: data.maintenanceItems.length > 0,
      group: "Huis",
      priority: "normaal",
    },
    {
      id: "emergency",
      title: "Noodkaart bruikbaar",
      detail: "Noodcontacten, huisinfo en documenten zijn snel bereikbaar.",
      href: "/noodkaart",
      done: data.householdContacts.some((contact) => contact.priority === "nood") && data.householdInfoItems.length > 0,
      group: "Huis",
      priority: "hoog",
    },
    {
      id: "home",
      title: "Smart home gekoppeld",
      detail: "Hue, Home Assistant of Google Home maakt huisbediening mogelijk.",
      href: "/home",
      done: data.hasHomeAssistantConfig || data.hasHueConfig || data.smartHomeIntegrations.some((item) => item.status === "configured"),
      group: "Koppelingen",
      priority: "normaal",
    },
    {
      id: "bank",
      title: "Bankkoppeling voorbereid",
      detail: "bunq of handmatige vaste lasten vullen de geldmodule.",
      href: "/geld",
      done: data.bankConnections.some((item) => item.status === "configured") || data.financeItems.length > 0,
      group: "Koppelingen",
      priority: "normaal",
    },
    {
      id: "integrations",
      title: "Koppelingen gecontroleerd",
      detail: "Controleer centraal of agenda, bank, taken en smart home goed staan.",
      href: "/koppelingen",
      done:
        data.calendarIntegrations.some((item) => item.status === "configured") ||
        data.bankConnections.some((item) => item.status === "configured") ||
        data.taskIntegrations.some((item) => item.status === "configured") ||
        data.hasHomeAssistantConfig ||
        data.hasHueConfig,
      group: "Koppelingen",
      priority: "normaal",
    },
  ];
}

export function setupProgress(steps: SetupStep[]) {
  const done = steps.filter((step) => step.done).length;
  return {
    done,
    total: steps.length,
    percent: steps.length === 0 ? 0 : Math.round((done / steps.length) * 100),
  };
}

export function buildSetupOverview(data: AppData): SetupOverview {
  const steps = buildSetupSteps(data);
  const progress = setupProgress(steps);
  const grouped = steps.reduce<Record<SetupStep["group"], SetupStep[]>>((groups, step) => {
    groups[step.group] = [...(groups[step.group] ?? []), step];
    return groups;
  }, {} as Record<SetupStep["group"], SetupStep[]>);
  const groupProgress = Object.entries(grouped).map(([group, groupSteps]) => {
    const done = groupSteps.filter((step) => step.done).length;
    return {
      group: group as SetupStep["group"],
      done,
      total: groupSteps.length,
      percent: groupSteps.length === 0 ? 0 : Math.round((done / groupSteps.length) * 100),
    };
  });
  const openSteps = steps.filter((step) => !step.done);
  const nextSteps = [...openSteps].sort(setupStepSort).slice(0, 4);
  const highImpactOpen = openSteps.filter((step) => step.priority === "hoog").sort(setupStepSort).slice(0, 3);
  const weakestGroup = [...groupProgress].sort((a, b) => a.percent - b.percent || groupWeight(a.group) - groupWeight(b.group))[0] ?? null;

  return {
    steps,
    progress,
    grouped,
    groupProgress,
    nextSteps,
    highImpactOpen,
    weakestGroup,
    nextAction: nextSteps[0] ?? null,
  };
}

function setupStepSort(a: SetupStep, b: SetupStep) {
  return priorityWeight(a.priority) - priorityWeight(b.priority) || groupWeight(a.group) - groupWeight(b.group) || a.title.localeCompare(b.title);
}

function priorityWeight(priority: SetupStep["priority"]) {
  return priority === "hoog" ? 0 : 1;
}

function groupWeight(group: SetupStep["group"]) {
  const order: Record<SetupStep["group"], number> = {
    Basis: 0,
    Dagelijks: 1,
    Planning: 2,
    Huis: 3,
    Koppelingen: 4,
  };
  return order[group];
}
