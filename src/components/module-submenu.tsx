import type { ReactNode } from "react";

export function ModuleSubmenu({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children: ReactNode;
}) {
  const popoverId = `module-submenu-${slugify(title)}`;

  return (
    <section className="module-submenu">
      <button className="module-submenu-collapsed" type="button" popoverTarget={popoverId}>
        <span className="module-submenu-trigger">
          <span className="summary-icon" aria-hidden="true">+</span>
          <span>
            <strong>{title}</strong>
            <small>{detail}</small>
          </span>
        </span>
      </button>
      <div className="app-popover module-submenu-popover" id={popoverId} popover="auto">
        <div className="module-submenu-overlay-head">
          <div>
            <span className="eyebrow">Nieuw</span>
            <h2>{title}</h2>
            <p className="muted">{detail}</p>
          </div>
          <button className="icon-button" type="button" popoverTarget={popoverId} popoverTargetAction="hide" aria-label={`${title} sluiten`} title={`${title} sluiten`}>
            ×
          </button>
        </div>
        {children}
      </div>
    </section>
  );
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}
