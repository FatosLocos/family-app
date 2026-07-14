"use client";

import {
  CalendarDays,
  CheckSquare,
  Landmark,
  MessageSquare,
  ShoppingBasket,
  Utensils,
  Zap,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { getQuickAddKindConfig, quickAddKindConfigs, type QuickAddKind } from "@/lib/quick-add-config";

type QuickAddAction = (formData: FormData) => void | Promise<void>;

const quickAddIcons: Record<QuickAddKind, ReactNode> = {
  task: <CheckSquare size={17} />,
  shopping: <ShoppingBasket size={17} />,
  note: <MessageSquare size={17} />,
  event: <CalendarDays size={17} />,
  meal: <Utensils size={17} />,
  finance: <Landmark size={17} />,
};

export function QuickAddSmartForm({ action }: { action: QuickAddAction }) {
  const [kind, setKind] = useState<QuickAddKind>("task");
  const config = getQuickAddKindConfig(kind);

  return (
    <form className="card form quick-add-form" action={action}>
      <div className="section-head">
        <div>
          <span className="eyebrow">Nieuwe invoer</span>
          <h2>Snelle invoer</h2>
          <p className="muted">Kies eerst wat je vastlegt. De app zet het daarna direct in de juiste module.</p>
        </div>
        <span className="summary-icon">
          <Zap size={18} />
        </span>
      </div>
      <fieldset className="quick-kind-picker">
        <legend>Type</legend>
        {quickAddKindConfigs.map((item) => (
          <QuickKindOption
            checked={kind === item.value}
            detail={item.detail}
            icon={quickAddIcons[item.value]}
            key={item.value}
            label={item.label}
            onChange={() => setKind(item.value)}
            value={item.value}
          />
        ))}
      </fieldset>
      <div className="quick-context-card">
        <strong>{config.label}</strong>
        <span>{config.help}</span>
      </div>
      <div className="field">
        <label htmlFor="quick-title">{config.titleLabel}</label>
        <input id="quick-title" name="title" required autoFocus placeholder={config.titlePlaceholder} />
      </div>
      <div className="field">
        <label htmlFor="quick-details">{config.detailsLabel}</label>
        <textarea id="quick-details" name="details" rows={4} placeholder={config.detailsPlaceholder} />
      </div>
      <div className="quick-field-grid">
        <div className="field">
          <label htmlFor="quick-category">{config.categoryLabel}</label>
          <input id="quick-category" name="category" placeholder={config.categoryPlaceholder} />
        </div>
        {config.showPriority && (
          <div className="field">
            <label htmlFor="quick-priority">Prioriteit</label>
            <select id="quick-priority" name="priority" defaultValue="normaal">
              <option value="laag">Laag</option>
              <option value="normaal">Normaal</option>
              <option value="hoog">Hoog</option>
            </select>
          </div>
        )}
        {config.dateLabel && (
          <div className="field">
            <label htmlFor="quick-due">{config.dateLabel}</label>
            <input id="quick-due" name="due_date" type="date" />
          </div>
        )}
        {config.showExpires && (
          <div className="field">
            <label htmlFor="quick-expires">Zichtbaar tot</label>
            <input id="quick-expires" name="expires_at" type="date" />
          </div>
        )}
      </div>
      {config.showPinned && (
        <label className="check-row">
          <input type="checkbox" name="pinned" />
          Bericht vastzetten op prikbord
        </label>
      )}
      <button className="button primary">{config.submitLabel}</button>
    </form>
  );
}

function QuickKindOption({
  value,
  label,
  detail,
  icon,
  checked,
  onChange,
}: {
  value: QuickAddKind;
  label: string;
  detail: string;
  icon: ReactNode;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label className="quick-kind-card">
      <input type="radio" name="kind" value={value} checked={checked} onChange={onChange} />
      <span>{icon}</span>
      <strong>{label}</strong>
      <small>{detail}</small>
    </label>
  );
}
