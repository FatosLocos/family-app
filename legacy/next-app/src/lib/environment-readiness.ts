export type EnvironmentVariableStatus = {
  key: string;
  label: string;
  present: boolean;
  secret: boolean;
};

export type EnvironmentGroupStatus = {
  id: string;
  title: string;
  description: string;
  variables: EnvironmentVariableStatus[];
  required: boolean;
  configured: number;
  total: number;
  ready: boolean;
};

export type EnvironmentReadiness = {
  mode: "local_postgres" | "demo";
  modeLabel: string;
  groups: EnvironmentGroupStatus[];
  requiredReady: number;
  requiredTotal: number;
  optionalReady: number;
  optionalTotal: number;
  readyPercent: number;
  nextAction: EnvironmentGroupStatus | null;
};

type EnvSource = Record<string, string | undefined>;

type VariableDefinition = {
  key: string;
  label: string;
  secret?: boolean;
};

type GroupDefinition = {
  id: string;
  title: string;
  description: string;
  required: boolean;
  variables: VariableDefinition[];
};

const groups: GroupDefinition[] = [
  {
    id: "local-db",
    title: "Lokale database",
    description: "Primaire opslag voor dev en VPS.",
    required: true,
    variables: [{ key: "DATABASE_URL", label: "Postgres connection string", secret: true }],
  },
  {
    id: "home-assistant",
    title: "Home Assistant",
    description: "Optionele server-side fallback wanneer er nog geen huishoudconfig is opgeslagen.",
    required: false,
    variables: [
      { key: "HOME_ASSISTANT_URL", label: "Base URL" },
      { key: "HOME_ASSISTANT_TOKEN", label: "Long-lived token", secret: true },
    ],
  },
  {
    id: "hue",
    title: "Philips Hue",
    description: "Optionele lokale live-test zonder opgeslagen bridgeconfig.",
    required: false,
    variables: [
      { key: "HUE_BRIDGE_URL", label: "Bridge URL" },
      { key: "HUE_APP_KEY", label: "App key", secret: true },
    ],
  },
  {
    id: "google-home",
    title: "Google Home / Nest",
    description: "OAuth clientgegevens voor Nest SDM en latere Google Home flows.",
    required: false,
    variables: [
      { key: "GOOGLE_HOME_CLIENT_ID", label: "OAuth client ID" },
      { key: "GOOGLE_HOME_CLIENT_SECRET", label: "OAuth client secret", secret: true },
      { key: "GOOGLE_HOME_PROJECT_ID", label: "Device Access project ID" },
    ],
  },
  {
    id: "outlook",
    title: "Outlook agenda",
    description: "Microsoft OAuth voor persoonlijke Outlook.com agenda's.",
    required: false,
    variables: [
      { key: "OUTLOOK_CALENDAR_CLIENT_ID", label: "OAuth client ID" },
      { key: "OUTLOOK_CALENDAR_CLIENT_SECRET", label: "OAuth client secret", secret: true },
      { key: "OUTLOOK_CALENDAR_TENANT_ID", label: "Tenant" },
    ],
  },
];

export function buildEnvironmentReadiness(env: EnvSource = process.env): EnvironmentReadiness {
  const statuses = groups.map((group) => {
    const variables = group.variables.map((variable) => ({
      key: variable.key,
      label: variable.label,
      secret: variable.secret ?? false,
      present: isFilled(env[variable.key]),
    }));
    const configured = variables.filter((variable) => variable.present).length;
    return {
      ...group,
      variables,
      configured,
      total: variables.length,
      ready: configured === variables.length,
    };
  });
  const localDatabase = statuses.find((group) => group.id === "local-db");
  const mode = localDatabase?.ready ? "local_postgres" : "demo";
  const requiredGroups = statuses.filter((group) => group.required);
  const optionalGroups = statuses.filter((group) => !group.required);
  const requiredReady = requiredGroups.filter((group) => group.ready).length;
  const optionalReady = optionalGroups.filter((group) => group.ready).length;
  const requiredTotal = requiredGroups.length;
  const optionalTotal = optionalGroups.length;
  const nextAction = requiredGroups.find((group) => !group.ready) ?? optionalGroups.find((group) => group.configured > 0 && !group.ready) ?? null;

  return {
    mode,
    modeLabel: mode === "local_postgres" ? "Lokale Postgres" : "Demo-modus",
    groups: statuses,
    requiredReady,
    requiredTotal,
    optionalReady,
    optionalTotal,
    readyPercent: Math.round(((requiredReady + optionalReady) / (requiredTotal + optionalTotal)) * 100),
    nextAction,
  };
}

function isFilled(value: string | undefined) {
  return Boolean(value && value.trim().length > 0);
}
