import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, Database, KeyRound, ShieldCheck, UsersRound } from "lucide-react";
import type { ReactNode } from "react";
import { openInviteCode, signIn, signUp } from "@/app/actions";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalUser, isLocalRegistrationOpen } from "@/lib/local-auth";
import { MissingConfig } from "@/components/auth-gate";
import { PasswordInput } from "@/components/password-input";
import { PublicThemeControl } from "@/components/public-theme-control";
import { SkipLink } from "@/components/skip-link";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams?: Promise<{ error?: string; success?: string; next?: string }>;
}) {
  const localMode = hasLocalDatabaseEnv();
  if (!localMode) return <MissingConfig />;
  if (localMode && (await getLocalUser())) redirect("/");
  const params = await searchParams;
  const localRegistrationOpen = localMode ? await isLocalRegistrationOpen() : true;

  return (
    <main className="shell" id="main-content" tabIndex={-1}>
      <SkipLink />
      <PublicThemeControl />
      <section className="container auth-page">
        <div className="auth-intro">
          <span className="eyebrow">Gezinsapp</span>
          <h1>Family App</h1>
          <p>
            Je data draait in je eigen Postgres-database. Log in, maak het eerste eigenaar-account aan of accepteer een uitnodiging van je huishouden.
          </p>
          <div className="auth-benefits">
            <AuthBenefit icon={<Database size={18} />} title="Eigen data" detail="Postgres onder eigen beheer" />
            <AuthBenefit icon={<UsersRound size={18} />} title="Gezinsleden" detail="Iedereen een eigen account en rol" />
            <AuthBenefit icon={<ShieldCheck size={18} />} title="Afgeschermd" detail="Modules zijn pas zichtbaar na login" />
          </div>
        </div>
        <div className="auth-workspace">
          <div className="auth-message-stack">
            {params?.error && <div className="error">{params.error}</div>}
            {params?.success && <div className="success">{params.success}</div>}
          </div>

          <div className="auth-card-grid">
            <form className="card form auth-card" action={signIn}>
              <div className="auth-card-head">
                <span className="auth-card-icon"><KeyRound size={18} /></span>
                <div>
                  <h2>Inloggen</h2>
                  <p className="muted">Voor bestaande gezinsaccounts.</p>
                </div>
              </div>
              <input type="hidden" name="next" value={params?.next ?? "/"} />
              <div className="field">
                <label htmlFor="login-email">E-mail</label>
                <input id="login-email" name="email" type="email" required />
              </div>
              <div className="field">
                <label htmlFor="login-password">Wachtwoord</label>
                <PasswordInput id="login-password" name="password" required autoComplete="current-password" />
              </div>
              <button className="button primary">Inloggen</button>
            </form>

            {localRegistrationOpen ? (
              <form className="card form auth-card" action={signUp}>
                <div className="auth-card-head">
                  <span className="auth-card-icon"><UsersRound size={18} /></span>
                  <div>
                    <h2>Eerste eigenaar</h2>
                    <p className="muted">{localMode ? "Alleen beschikbaar zolang er nog geen account bestaat." : "Maak je account en start daarna je huishouden."}</p>
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="signup-name">Naam</label>
                  <input id="signup-name" name="full_name" />
                </div>
                <div className="field">
                  <label htmlFor="signup-email">E-mail</label>
                  <input id="signup-email" name="email" type="email" required />
                </div>
                <div className="field">
                  <label htmlFor="signup-password">Wachtwoord</label>
                  <PasswordInput id="signup-password" name="password" minLength={8} required autoComplete="new-password" />
                </div>
                <button className="button">Eigenaar-account maken</button>
              </form>
            ) : (
              <div className="card auth-card auth-closed">
                <div className="auth-card-head">
                  <span className="auth-card-icon"><ShieldCheck size={18} /></span>
                  <div>
                    <h2>Registratie gesloten</h2>
                    <p className="muted">Het eerste eigenaar-account bestaat al. Nieuwe gezinsleden komen binnen via een uitnodiging.</p>
                  </div>
                </div>
                <span className="status">Vraag de eigenaar om een invite-code</span>
              </div>
            )}

            <form className="card form auth-card auth-invite" action={openInviteCode}>
              <div className="auth-card-head">
                <span className="auth-card-icon"><ArrowRight size={18} /></span>
                <div>
                  <h2>Uitnodiging</h2>
                  <p className="muted">Heb je een code gekregen? Open direct de juiste uitnodigingspagina.</p>
                </div>
              </div>
              <div className="field">
                <label htmlFor="invite-code">Invite-code</label>
                <input id="invite-code" name="invite_code" placeholder="Bijv. ABCD-1234" />
              </div>
              <button className="button">Code openen</button>
            </form>
          </div>
          <Link href="/" className="auth-back-link">
            Terug naar start
          </Link>
        </div>
      </section>
    </main>
  );
}

function AuthBenefit({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return (
    <div className="auth-benefit">
      <span>{icon}</span>
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}
