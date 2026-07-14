import Link from "next/link";
import { ArrowRight, CalendarDays, CheckSquare, Home, PackagePlus, ShoppingBasket, UsersRound, WalletCards } from "lucide-react";
import { applyStarterPack } from "@/app/actions";
import { buildSetupOverview } from "@/lib/setup";
import { buildStarterPackSummary } from "@/lib/starter-pack";
import type { AppData } from "@/lib/types";

const starterActions = [
  { href: "/instellingen", label: "Gezinsleden", detail: "Nodig iedereen uit", icon: UsersRound },
  { href: "/taken", label: "Taken", detail: "Leg vaste acties vast", icon: CheckSquare },
  { href: "/boodschappen", label: "Boodschappen", detail: "Start de gedeelde lijst", icon: ShoppingBasket },
  { href: "/agenda", label: "Agenda", detail: "Plan of koppel Outlook", icon: CalendarDays },
  { href: "/geld", label: "Geld", detail: "Vaste lasten en budget", icon: WalletCards },
];

export function GettingStartedPanel({ data, localMode = false }: { data: AppData; localMode?: boolean }) {
  const overview = buildSetupOverview(data);
  const starterSummary = buildStarterPackSummary();
  const visibleSteps = overview.highImpactOpen.length > 0 ? overview.highImpactOpen : overview.nextSteps;

  if (overview.progress.percent >= 70 || visibleSteps.length === 0) return null;

  return (
    <section className="getting-started" aria-labelledby="getting-started-title">
      <div className="getting-started-main">
        <div>
          <span className="eyebrow">Aan de slag</span>
          <h2 id="getting-started-title">Maak je gezinsapp bruikbaar voor dagelijks gebruik</h2>
          <p>
            Begin met de onderdelen die meteen waarde geven: toegang voor gezinsleden, taken, boodschappen, agenda en geld.
          </p>
        </div>
        <div className="getting-started-progress">
          <strong>{overview.progress.percent}%</strong>
          <span>{overview.progress.done}/{overview.progress.total} ingericht</span>
          <div className="setup-bar" aria-hidden="true">
            <span style={{ width: `${overview.progress.percent}%` }} />
          </div>
        </div>
      </div>
      <div className="getting-started-grid">
        <div className="getting-started-steps">
          {localMode && (
            <form className="getting-started-starter" action={applyStarterPack}>
              <span>
                <PackagePlus size={18} />
              </span>
              <div>
                <strong>Starterpakket vullen</strong>
                <small>Voegt {starterSummary.totalItems} basisitems toe voor routines, boodschappen, geld, huisinfo en documenten.</small>
              </div>
              <button className="button primary">Toevoegen</button>
            </form>
          )}
          {visibleSteps.slice(0, 3).map((step) => (
            <Link className="getting-started-step" href={step.href} key={step.id}>
              <span>{step.group}</span>
              <strong>{step.title}</strong>
              <small>{step.detail}</small>
              <ArrowRight size={16} />
            </Link>
          ))}
        </div>
        <div className="starter-actions" aria-label="Snelle startacties">
          {starterActions.map(({ href, label, detail, icon: Icon }) => (
            <Link className="starter-action" href={href} key={href}>
              <span>
                <Icon size={17} />
              </span>
              <strong>{label}</strong>
              <small>{detail}</small>
            </Link>
          ))}
          <Link className="starter-action emphasized" href="/inrichting">
            <span>
              <Home size={17} />
            </span>
            <strong>Volledige inrichting</strong>
            <small>Open de checklist</small>
          </Link>
        </div>
      </div>
    </section>
  );
}
