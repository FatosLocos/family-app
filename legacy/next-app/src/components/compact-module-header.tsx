import type { ReactNode } from "react";

export function CompactModuleHeader({
  eyebrow,
  title,
  children,
  stats = [],
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
  stats?: Array<{ label: string; value: ReactNode }>;
}) {
  return (
    <div className="compact-module-head">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        {children && <p className="muted">{children}</p>}
      </div>
      {stats.length > 0 && (
        <div className="compact-head-stats">
          {stats.map((stat) => (
            <span key={stat.label}>
              <strong>{stat.value}</strong> {stat.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
