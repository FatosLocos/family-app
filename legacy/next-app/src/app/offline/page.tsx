import Link from "next/link";
import { CalendarDays, Home, ShieldAlert, ShoppingBasket, WifiOff, Zap } from "lucide-react";
import type { ReactNode } from "react";

export const dynamic = "force-static";

export default function OfflinePage() {
  return (
    <main className="offline-page">
      <section className="card offline-card">
        <div className="offline-head">
          <span className="summary-icon">
            <WifiOff size={20} />
          </span>
          <span className="status accent">Offline</span>
        </div>
        <div>
          <h1>Je bent offline</h1>
          <p className="muted">
            Nieuwe wijzigingen worden pas betrouwbaar opgeslagen zodra je verbinding terug is. Eerder geopende pagina's kunnen nog uit de cache beschikbaar zijn.
          </p>
        </div>
        <div className="offline-route-grid">
          <OfflineRoute icon={<Home size={17} />} title="Dashboard" href="/" />
          <OfflineRoute icon={<CalendarDays size={17} />} title="Vandaag" href="/vandaag" />
          <OfflineRoute icon={<ShoppingBasket size={17} />} title="Boodschappen" href="/boodschappen" />
          <OfflineRoute icon={<Zap size={17} />} title="Snel" href="/snel" />
          <OfflineRoute icon={<ShieldAlert size={17} />} title="Noodkaart" href="/noodkaart" />
        </div>
        <div className="quick-actions">
          <Link className="button primary" href="/">Opnieuw proberen</Link>
          <Link className="button" href="/data">Data & backup</Link>
        </div>
      </section>
    </main>
  );
}

function OfflineRoute({ icon, title, href }: { icon: ReactNode; title: string; href: string }) {
  return (
    <Link className="offline-route" href={href}>
      <span>{icon}</span>
      <strong>{title}</strong>
    </Link>
  );
}
