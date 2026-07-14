import type { ReactNode } from "react";

export function ModuleLayout({
  children,
  aside,
  asideLabel = "Module-acties",
  className,
}: {
  children: ReactNode;
  aside?: ReactNode;
  asideLabel?: string;
  className?: string;
}) {
  return (
    <section className={["module-page", className].filter(Boolean).join(" ")}>
      <div className="module-main">{children}</div>
      {aside && (
        <aside className="module-side-panel" aria-label={asideLabel}>
          {aside}
        </aside>
      )}
    </section>
  );
}
