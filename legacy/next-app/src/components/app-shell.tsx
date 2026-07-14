import Link from "next/link";
import { Home, LogOut } from "lucide-react";
import { signOut } from "@/app/actions";
import { MainNavigation, MobileTabBar } from "@/components/navigation";
import { SkipLink } from "@/components/skip-link";
import { ThemeToggle } from "@/components/theme-toggle";
import { InstantSearchEnhancer } from "@/components/instant-search-enhancer";
import { hasLocalDatabaseEnv } from "@/lib/env";

export function AppShell({ children, demo = false }: { children: React.ReactNode; demo?: boolean }) {
  const localMode = hasLocalDatabaseEnv();

  return (
    <div className="shell">
      <InstantSearchEnhancer />
      <SkipLink />
      <header className="topbar">
        <div className="container topbar-inner">
          <Link href="/" className="brand" aria-label="Naar dashboard">
            <span className="brand-mark">
              <Home size={19} />
            </span>
            <span>Family App</span>
          </Link>
          <MainNavigation />
          {demo ? (
            <div className="app-actions">
              <ThemeToggle />
              <span className="status">Demo</span>
            </div>
          ) : (
            <div className="app-actions">
              {localMode && <span className="status">Lokale database</span>}
              <ThemeToggle />
              <form action={signOut}>
                <button className="icon-button" title="Uitloggen" aria-label="Uitloggen">
                  <LogOut size={18} />
                </button>
              </form>
            </div>
          )}
        </div>
      </header>
      <main className="main" id="main-content" tabIndex={-1}>
        <div className="container">
          {children}
        </div>
      </main>
      {!demo && (
        <MobileTabBar />
      )}
    </div>
  );
}
