import { redirect } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { HomeAssistantPanel } from "@/components/home-assistant-panel";
import { HuePanel } from "@/components/hue-panel";
import { GoogleHomePanel } from "@/components/google-home-panel";
import { getAppData, getUser } from "@/lib/local-data";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { hasHueEnv, hasLocalDatabaseEnv } from "@/lib/env";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    const data = await getLocalAppData();
    return (
      <AppShell>
        <div className="grid">
          <CompactModuleHeader
            eyebrow="Huis"
            title="Home"
            stats={[
              { label: "Home Assistant", value: data.hasHomeAssistantConfig ? "actief" : "uit" },
              { label: "Google Home", value: googleHomeIntegrationCount(data) },
            ]}
          >
            Bedien slimme apparaten en bekijk de status van je koppelingen.
          </CompactModuleHeader>
          <HomeAssistantPanel configured={data.hasHomeAssistantConfig} />
          <GoogleHomePanel data={data} />
        </div>
      </AppShell>
    );
  }
  if (!hasLocalDatabaseEnv()) {
    if (hasHueEnv()) {
      return (
        <AppShell demo>
          <div className="grid">
            <CompactModuleHeader eyebrow="Huis" title="Home" stats={[{ label: "Hue", value: "actief" }]}>Bedien slimme apparaten en bekijk de status van je koppelingen.</CompactModuleHeader>
            <HuePanel configured />
          </div>
        </AppShell>
      );
    }
    return <DemoWorkspace view="home" />;
  }
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");

  return (
    <AppShell>
      <div className="grid">
        <CompactModuleHeader
          eyebrow="Huis"
          title="Home"
          stats={[
            { label: "Hue", value: data.hasHueConfig ? "actief" : "uit" },
            { label: "Home Assistant", value: data.hasHomeAssistantConfig || Boolean(process.env.HOME_ASSISTANT_URL) ? "actief" : "uit" },
            { label: "Google Home", value: googleHomeIntegrationCount(data) },
          ]}
        >
          Bedien slimme apparaten en bekijk de status van je koppelingen.
        </CompactModuleHeader>
        {data.hasHueConfig ? (
          <HuePanel configured={data.hasHueConfig} />
        ) : (
          <>
          <HomeAssistantPanel configured={data.hasHomeAssistantConfig || Boolean(process.env.HOME_ASSISTANT_URL)} />
          <GoogleHomePanel data={data} />
          </>
        )}
      </div>
    </AppShell>
  );
}

function googleHomeIntegrationCount(data: { smartHomeIntegrations: Array<{ provider: string }> }) {
  return data.smartHomeIntegrations.filter((integration) => integration.provider === "google_home").length;
}
