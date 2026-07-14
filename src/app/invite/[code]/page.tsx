import { acceptInvite } from "@/app/actions";
import { PasswordInput } from "@/components/password-input";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalUser } from "@/lib/local-auth";

export const dynamic = "force-dynamic";

export default async function InvitePage({
  params,
  searchParams,
}: {
  params: Promise<{ code: string }>;
  searchParams?: Promise<{ error?: string }>;
}) {
  const { code } = await params;
  const query = await searchParams;
  const accept = acceptInvite.bind(null, code);
  const localMode = hasLocalDatabaseEnv();
  const localUser = localMode ? await getLocalUser() : null;

  return (
    <main className="shell">
      <section className="container hero">
        <form className="card form" action={accept} style={{ maxWidth: 520 }}>
          <h1 style={{ fontSize: 42 }}>Uitnodiging</h1>
          <p className="muted">
            {localUser
              ? `Accepteer invite-code ${code} met je huidige account.`
              : `Maak een lokaal account aan om invite-code ${code} te accepteren.`}
          </p>
          {query?.error && <div className="error">{query.error}</div>}
          {localMode && !localUser && (
            <>
              <div className="field">
                <label htmlFor="invite-name">Naam</label>
                <input id="invite-name" name="full_name" />
              </div>
              <div className="field">
                <label htmlFor="invite-email">E-mail</label>
                <input id="invite-email" name="email" type="email" required />
              </div>
              <div className="field">
                <label htmlFor="invite-password">Wachtwoord</label>
                <PasswordInput id="invite-password" name="password" minLength={8} required autoComplete="new-password" />
              </div>
            </>
          )}
          <button className="button primary">Uitnodiging accepteren</button>
        </form>
      </section>
    </main>
  );
}
