import Link from "next/link";
import { PublicThemeControl } from "@/components/public-theme-control";
import { SkipLink } from "@/components/skip-link";
import { hasLocalDatabaseEnv } from "@/lib/env";

export function MissingConfig() {
  return (
    <main className="shell" id="main-content" tabIndex={-1}>
      <SkipLink />
      <PublicThemeControl />
      <section className="container hero">
        <div>
          <h1>Family App</h1>
          <p>
            De app-code staat klaar. Configureer een Postgres-database om login, database en gezinsdata te activeren.
          </p>
          <div className="grid" style={{ maxWidth: 520 }}>
            <div className="card">
              <h2>Nodig</h2>
              <p className="muted">DATABASE_URL voor de Postgres-verbinding.</p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

export function Landing() {
  return (
    <main className="shell" id="main-content" tabIndex={-1}>
      <SkipLink />
      <PublicThemeControl />
      <section className="container hero">
        <div>
          <h1>Family App</h1>
          <p>
            Een gedeeld gezinsdashboard voor taken, boodschappen, geld, agenda en je slimme huis.
            {!hasLocalDatabaseEnv() && " Je bekijkt nu de demo-modus zonder database."}
          </p>
          {hasLocalDatabaseEnv() ? (
            <Link className="button primary" href="/login">
              Inloggen of account maken
            </Link>
          ) : (
            <Link className="button primary" href="/">
              Demo bekijken
            </Link>
          )}
        </div>
      </section>
    </main>
  );
}
