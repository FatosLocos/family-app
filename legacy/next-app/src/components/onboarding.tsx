import { createHousehold } from "@/app/actions";
import { PublicThemeControl } from "@/components/public-theme-control";
import { SkipLink } from "@/components/skip-link";
import { CalendarDays, Home, Moon, ShoppingCart, UsersRound } from "lucide-react";

export function Onboarding() {
  return (
    <main className="shell" id="main-content" tabIndex={-1}>
      <SkipLink />
      <PublicThemeControl />
      <section className="container onboarding-page">
        <div className="onboarding-intro">
          <span className="eyebrow">Eerste inrichting</span>
          <h1>Start je huishouden</h1>
          <p>Maak het gezinsprofiel aan en zet meteen de standaarden goed voor dashboard, weekplanning, boodschappen en stille uren.</p>
          <div className="onboarding-preview">
            <OnboardingPreview icon={<UsersRound size={18} />} title="Gezin" detail="Eigen huishouden met rollen en invites" />
            <OnboardingPreview icon={<CalendarDays size={18} />} title="Planning" detail="Vandaag en week starten direct goed" />
            <OnboardingPreview icon={<Home size={18} />} title="Modules" detail="Klaar voor taken, boodschappen, geld en huis" />
          </div>
        </div>
        <form className="card form onboarding-card" action={createHousehold}>
          <div className="section-head">
            <div>
              <h2>Basisgegevens</h2>
              <p className="muted">Deze keuzes kun je later aanpassen via Instellingen.</p>
            </div>
            <span className="summary-icon">
              <Home size={18} />
            </span>
          </div>
          <div className="onboarding-form-grid">
            <div className="field">
              <label htmlFor="name">Naam huishouden</label>
              <input id="name" name="name" defaultValue="Ons gezin" required />
            </div>
            <div className="field">
              <label htmlFor="default-dashboard">Startbeeld</label>
              <select id="default-dashboard" name="default_dashboard" defaultValue="vandaag">
                <option value="vandaag">Vandaag</option>
                <option value="compact">Compact dashboard</option>
                <option value="uitgebreid">Uitgebreid dashboard</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="week-start">Week begint op</label>
              <select id="week-start" name="week_starts_on" defaultValue="monday">
                <option value="monday">Maandag</option>
                <option value="sunday">Zondag</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="default-shopping-store">Standaard winkel</label>
              <input id="default-shopping-store" name="default_shopping_store" placeholder="Bijv. Albert Heijn, Jumbo, Lidl" />
            </div>
          </div>
          <div className="onboarding-preference-strip">
            <div>
              <Moon size={18} />
              <span>
                <strong>Stille uren</strong>
                <small>Voor toekomstige meldingen en dagoverzichten.</small>
              </span>
            </div>
            <div className="form-row">
              <div className="field">
                <label htmlFor="quiet-hours-start">Vanaf</label>
                <input id="quiet-hours-start" name="quiet_hours_start" type="time" defaultValue="22:00" />
              </div>
              <div className="field">
                <label htmlFor="quiet-hours-end">Tot</label>
                <input id="quiet-hours-end" name="quiet_hours_end" type="time" defaultValue="07:00" />
              </div>
            </div>
          </div>
          <div className="onboarding-next">
            <div>
              <ShoppingCart size={18} />
              <span>Na aanmaken kom je in de app terecht en kun je gezinsleden uitnodigen via Instellingen.</span>
            </div>
            <button className="button primary">Huishouden maken</button>
          </div>
        </form>
      </section>
    </main>
  );
}

function OnboardingPreview({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return (
    <div className="onboarding-preview-card">
      <span>{icon}</span>
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}
