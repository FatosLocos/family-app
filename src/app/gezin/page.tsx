import { redirect } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, Home, Phone, ShieldCheck, UsersRound } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { HouseholdContactForm, HouseholdInfoForm } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { ModuleLayout } from "@/components/module-layout";
import { HouseholdContactList, HouseholdInfoList } from "@/components/module-lists";
import { demoData } from "@/lib/demo-data";
import { buildEmergencyReadiness } from "@/lib/emergency-readiness";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";
import { getAppData, getUser } from "@/lib/local-data";

export const dynamic = "force-dynamic";

export default async function FamilyPage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <FamilyContent data={await getLocalAppData()} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="instellingen" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <FamilyContent data={data} />;
}

function FamilyContent({ data, demo = false }: { data: typeof demoData; demo?: boolean }) {
  const emergencyReadiness = buildEmergencyReadiness(data);
  const emergencyContacts = data.householdContacts.filter((contact) => contact.priority === "nood");
  const importantContacts = data.householdContacts.filter((contact) => contact.priority === "belangrijk");
  const infoCategories = Array.from(new Set(data.householdInfoItems.map((item) => item.category).filter(Boolean)));
  const firstEmergencyContact = emergencyContacts[0] ?? importantContacts[0] ?? data.householdContacts[0] ?? null;

  return (
    <AppShell demo={demo}>
      <ModuleLayout
        asideLabel="Gezinsacties"
        aside={demo ? <DemoPanel /> : <><ModuleSubmenu title="Contact toevoegen" detail="Belangrijk contact voor het gezin opslaan"><HouseholdContactForm /></ModuleSubmenu><ModuleSubmenu title="Huisinformatie toevoegen" detail="Praktische gezinsinformatie vastleggen"><HouseholdInfoForm /></ModuleSubmenu></>}
      >
        <div className="grid">
          <CompactModuleHeader
            eyebrow="Huis"
            title="Gezin"
            stats={[
              { label: "gezinsleden", value: data.members.length },
              { label: "noodcontacten", value: emergencyContacts.length },
              { label: "gevoelige items", value: emergencyReadiness.sensitiveItemCount },
            ]}
          >
            Gezinsleden, noodcontacten en belangrijke huisinformatie bij elkaar.
          </CompactModuleHeader>
          <section className="family-control card">
            <div className="section-head">
              <div>
                <span className="eyebrow">Gezinsregie</span>
                <h2>Wie hoort erbij en wat is kritiek?</h2>
                <p className="muted">Een compact beeld van leden, noodcontacten en belangrijke huisinformatie.</p>
              </div>
              <span className="summary-icon">
                <ShieldCheck size={18} />
              </span>
            </div>
            <div className="family-control-grid">
              <FamilyMetric icon={<UsersRound size={17} />} label="Gezinsleden" value={data.members.length} detail={`${data.members.filter((member) => member.role === "owner" || member.role === "admin").length} beheerders`} />
              <FamilyMetric icon={<Phone size={17} />} label="Noodcontacten" value={emergencyContacts.length} detail={firstEmergencyContact ? firstEmergencyContact.name : "Nog geen contact"} />
              <FamilyMetric icon={<Home size={17} />} label="Huisinfo" value={data.householdInfoItems.length} detail={`${infoCategories.length} categorieen`} />
              <FamilyMetric icon={<AlertTriangle size={17} />} label="Gevoelig" value={emergencyReadiness.sensitiveItemCount} detail="Info en documenten" />
            </div>
            <div className="family-next-row">
              <div>
                <strong>Noodkaart compleetheid</strong>
                <p className="muted">{emergencyReadiness.doneCount}/{emergencyReadiness.totalCount} basispunten ingevuld voor noodgevallen.</p>
                <div className="setup-bar" aria-hidden="true">
                  <span style={{ width: `${emergencyReadiness.score}%` }} />
                </div>
              </div>
              <div className="family-action-stack">
                {firstEmergencyContact?.phone ? (
                  <a className="button primary" href={`tel:${firstEmergencyContact.phone}`}>
                    <Phone size={17} /> {firstEmergencyContact.name} bellen
                  </a>
                ) : (
                  <Link className="button primary" href="/noodkaart">
                    <AlertTriangle size={17} /> Noodkaart openen
                  </Link>
                )}
                <Link className="button" href="/noodkaart">Noodkaart</Link>
              </div>
            </div>
            <div className="family-missing-row">
              {emergencyReadiness.missing.slice(0, 3).map((item) => (
                <Link className="family-missing-item" href={item.href} key={item.id}>
                  <span>{item.group === "contact" ? "Contact" : item.group === "document" ? "Document" : "Info"}</span>
                  <strong>{item.label}</strong>
                </Link>
              ))}
              {emergencyReadiness.missing.length === 0 && (
                <div className="family-missing-item complete">
                  <span>Noodkaart</span>
                  <strong>Basisinformatie compleet</strong>
                </div>
              )}
            </div>
          </section>
          <HouseholdContactList data={data} readOnly={demo} />
          <HouseholdInfoList data={data} readOnly={demo} />
        </div>
      </ModuleLayout>
    </AppShell>
  );
}

function FamilyMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="family-metric">
      <span className="family-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function DemoPanel() {
  return (
    <div className="card">
      <h2>Demo-modus</h2>
      <p className="muted">Log in met een databaseconfiguratie om gezinscontacten en huisinformatie lokaal op te slaan.</p>
    </div>
  );
}
