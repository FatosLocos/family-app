"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useMemo, useState, useTransition } from "react";
import { setRecurringTransactionRule } from "@/app/actions";
import type { RecurringCashflowTrendPoint, RecurringCostInsight } from "@/lib/finance-insights";
import { money, shortDate } from "@/lib/format";

type RecurringCostGroupId = "income" | "fixed" | "insurance" | "credit" | "subscription" | "tax" | "other";
type EditableRecurringCostGroupId = Exclude<RecurringCostGroupId, "income">;

const recurringCostGroupDefinitions: Array<{ id: RecurringCostGroupId; label: string }> = [
  { id: "income", label: "Inkomsten" },
  { id: "fixed", label: "Vaste lasten" },
  { id: "insurance", label: "Verzekeringen" },
  { id: "credit", label: "Leningen & Credits" },
  { id: "subscription", label: "Abonnementen" },
  { id: "tax", label: "Belastingen" },
  { id: "other", label: "Overig" },
];
const collapsedStorageKey = "family_app.recurringCostGroups.collapsed";

export function RecurringCostGroups({ insights, trend }: { insights: RecurringCostInsight[]; trend: RecurringCashflowTrendPoint[] }) {
  const [groupOverrides, setGroupOverrides] = useState<Record<string, EditableRecurringCostGroupId>>({});
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [draggedKey, setDraggedKey] = useState<string | null>(null);
  const [activeDropGroup, setActiveDropGroup] = useState<RecurringCostGroupId | null>(null);
  const [isPending, startTransition] = useTransition();
  const grouped = useMemo(() => groupRecurringCosts(insights, groupOverrides), [insights, groupOverrides]);
  const incomeTotal = insights.filter((item) => item.direction === "income").reduce((sum, item) => sum + item.monthlyEstimateCents, 0);
  const expenseTotal = insights.filter((item) => item.direction === "expense").reduce((sum, item) => sum + item.monthlyEstimateCents, 0);
  const netTotal = incomeTotal - expenseTotal;

  useEffect(() => {
    const stored = window.localStorage.getItem(collapsedStorageKey);
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored) as Record<string, boolean>;
      setCollapsedGroups(parsed);
    } catch {
      window.localStorage.removeItem(collapsedStorageKey);
    }
  }, []);

  function moveItem(item: RecurringCostInsight, groupId: EditableRecurringCostGroupId) {
    if (item.direction === "income") return;
    const previousGroupId = groupOverrides[item.key] ?? editableRecurringCostGroupId(item);
    if (previousGroupId === groupId) return;
    setGroupOverrides((current) => ({ ...current, [item.key]: groupId }));
    startTransition(() => {
      void saveRecurringGroup(item, groupId).catch(() => {
        setGroupOverrides((current) => ({ ...current, [item.key]: previousGroupId }));
      });
    });
  }

  function droppedOnGroup(groupId: RecurringCostGroupId) {
    const item = insights.find((candidate) => candidate.key === draggedKey);
    setDraggedKey(null);
    setActiveDropGroup(null);
    if (item && groupId !== "income") moveItem(item, groupId);
  }

  function toggleGroup(groupId: RecurringCostGroupId) {
    setCollapsedGroups((current) => {
      const next = { ...current, [groupId]: !current[groupId] };
      window.localStorage.setItem(collapsedStorageKey, JSON.stringify(next));
      return next;
    });
  }

  return (
    <>
      <div className="section-head">
        <div>
          <h2>Terugkerend overzicht</h2>
          <p className="muted">Inkomsten worden apart getoond. Sleep kostkaarten naar een andere groep om je vaste kosten handmatig te ordenen.</p>
        </div>
        <div className="recurring-summary-statuses">
          <span className="status amount-status positive">+{money(incomeTotal)} p/m</span>
          <span className="status amount-status negative">-{money(expenseTotal)} p/m</span>
          <span className={netTotal >= 0 ? "status amount-status positive" : "status amount-status negative"}>{money(netTotal)} netto</span>
        </div>
      </div>
      {insights.length === 0 ? (
        <p className="empty-state">Nog geen duidelijke terugkerende inkomsten of kosten gevonden.</p>
      ) : (
        <div className="recurring-cost-groups" aria-busy={isPending}>
          <RecurringTrendChart trend={trend} />
          {grouped.map((group) => (
            <section
              className={activeDropGroup === group.id ? "recurring-cost-group drop-active" : "recurring-cost-group"}
              key={group.id}
              onDragOver={(event) => {
                if (group.id === "income") return;
                event.preventDefault();
                setActiveDropGroup(group.id);
              }}
              onDragLeave={() => setActiveDropGroup(null)}
              onDrop={(event) => {
                event.preventDefault();
                droppedOnGroup(group.id);
              }}
            >
              <button
                className="recurring-cost-group-head recurring-cost-group-toggle"
                type="button"
                aria-expanded={!collapsedGroups[group.id]}
                onClick={() => toggleGroup(group.id)}
              >
                <div className="recurring-cost-group-title">
                  <ChevronDown className={collapsedGroups[group.id] ? "collapse-chevron collapsed" : "collapse-chevron"} size={16} />
                  <div>
                  <h3>{group.label}</h3>
                  <p className="muted">{group.items.length} herkend</p>
                  </div>
                </div>
                <span className={group.id === "income" ? "status amount-status positive" : "status amount-status negative"}>
                  {group.id === "income" ? "+" : "-"}{money(group.totalCents)} p/m
                </span>
              </button>
              {!collapsedGroups[group.id] && (
                <ul className="list">
                  {group.items.map((item) => (
                    <RecurringCostRow
                      item={item}
                      groups={recurringCostGroupDefinitions}
                      isDragging={draggedKey === item.key}
                      key={item.key}
                      onMove={moveItem}
                      onDragStart={() => setDraggedKey(item.key)}
                      onDragEnd={() => {
                        setDraggedKey(null);
                        setActiveDropGroup(null);
                      }}
                    />
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}
    </>
  );
}

function RecurringTrendChart({ trend }: { trend: RecurringCashflowTrendPoint[] }) {
  const [activePoint, setActivePoint] = useState<{ point: RecurringCashflowTrendPoint; x: number; y: number } | null>(null);
  const chartWidth = 640;
  const chartHeight = 220;
  const padding = { top: 18, right: 18, bottom: 38, left: 52 };
  const plotWidth = chartWidth - padding.left - padding.right;
  const plotHeight = chartHeight - padding.top - padding.bottom;
  const maxValue = Math.max(1, ...trend.flatMap((point) => [point.incomeCents, point.expenseCents, Math.abs(point.netCents)]));

  function x(index: number) {
    return padding.left + (trend.length <= 1 ? plotWidth / 2 : (plotWidth / (trend.length - 1)) * index);
  }

  function y(value: number) {
    return padding.top + plotHeight - (Math.max(0, value) / maxValue) * plotHeight;
  }

  function pointsFor(key: "incomeCents" | "expenseCents" | "netCents") {
    return trend.map((point, index) => `${x(index)},${y(Math.abs(point[key]))}`).join(" ");
  }

  const latest = trend[trend.length - 1] ?? null;
  const showPoint = (point: RecurringCashflowTrendPoint, pointX: number, pointY: number) => setActivePoint({ point, x: pointX, y: pointY });

  return (
    <div className="recurring-trend-panel">
      <div className="recurring-trend-head">
        <div>
          <h3>Trend terugkerend</h3>
          <p className="muted">Werkelijk geboekte terugkerende transacties per maand.</p>
        </div>
        {latest && (
          <div className="recurring-trend-latest">
            <span className="status amount-status positive">+{money(latest.incomeCents)}</span>
            <span className="status amount-status negative">-{money(latest.expenseCents)}</span>
            <span className={latest.netCents >= 0 ? "status amount-status positive" : "status amount-status negative"}>{money(latest.netCents)}</span>
          </div>
        )}
      </div>
      <div className="recurring-trend-chart" aria-label="Trendgrafiek terugkerende inkomsten en kosten">
        <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img">
          <title>Trend terugkerende inkomsten en kosten</title>
          {[0, 0.5, 1].map((step) => {
            const lineY = padding.top + plotHeight - plotHeight * step;
            return <line className="trend-grid-line" key={step} x1={padding.left} x2={chartWidth - padding.right} y1={lineY} y2={lineY} />;
          })}
          <polyline className="trend-line income" points={pointsFor("incomeCents")} />
          <polyline className="trend-line expense" points={pointsFor("expenseCents")} />
          <polyline className="trend-line net" points={pointsFor("netCents")} />
          {trend.map((point, index) => (
            <g key={point.month}>
              <circle
                className="trend-dot income"
                cx={x(index)}
                cy={y(point.incomeCents)}
                r="4"
                tabIndex={0}
                role="img"
                aria-label={`${point.label}: inkomsten ${money(point.incomeCents)}, kosten ${money(point.expenseCents)}, netto ${money(point.netCents)}`}
                onClick={() => showPoint(point, x(index), y(point.incomeCents))}
                onFocus={() => showPoint(point, x(index), y(point.incomeCents))}
                onBlur={() => setActivePoint(null)}
                onMouseEnter={() => showPoint(point, x(index), y(point.incomeCents))}
                onMouseLeave={() => setActivePoint(null)}
              />
              <circle
                className="trend-dot expense"
                cx={x(index)}
                cy={y(point.expenseCents)}
                r="4"
                tabIndex={0}
                role="img"
                aria-label={`${point.label}: inkomsten ${money(point.incomeCents)}, kosten ${money(point.expenseCents)}, netto ${money(point.netCents)}`}
                onClick={() => showPoint(point, x(index), y(point.expenseCents))}
                onFocus={() => showPoint(point, x(index), y(point.expenseCents))}
                onBlur={() => setActivePoint(null)}
                onMouseEnter={() => showPoint(point, x(index), y(point.expenseCents))}
                onMouseLeave={() => setActivePoint(null)}
              />
              <circle
                className="trend-dot net"
                cx={x(index)}
                cy={y(Math.abs(point.netCents))}
                r="3.5"
                tabIndex={0}
                role="img"
                aria-label={`${point.label}: inkomsten ${money(point.incomeCents)}, kosten ${money(point.expenseCents)}, netto ${money(point.netCents)}`}
                onClick={() => showPoint(point, x(index), y(Math.abs(point.netCents)))}
                onFocus={() => showPoint(point, x(index), y(Math.abs(point.netCents)))}
                onBlur={() => setActivePoint(null)}
                onMouseEnter={() => showPoint(point, x(index), y(Math.abs(point.netCents)))}
                onMouseLeave={() => setActivePoint(null)}
              />
              <text className="trend-month-label" x={x(index)} y={chartHeight - 12}>{point.label}</text>
            </g>
          ))}
          <text className="trend-axis-label" x={padding.left} y={14}>{money(maxValue)}</text>
          <text className="trend-axis-label" x={padding.left} y={padding.top + plotHeight + 14}>€ 0</text>
        </svg>
        {activePoint && (
          <div
            className="recurring-trend-tooltip"
            role="status"
            style={{
              left: `clamp(8px, ${(activePoint.x / chartWidth) * 100}%, calc(100% - 168px))`,
              top: `clamp(8px, ${(activePoint.y / chartHeight) * 100}%, calc(100% - 92px))`,
            }}
          >
            <strong>{activePoint.point.label}</strong>
            <span>Inkomsten {money(activePoint.point.incomeCents)}</span>
            <span>Kosten {money(activePoint.point.expenseCents)}</span>
            <span>Netto {money(activePoint.point.netCents)}</span>
          </div>
        )}
      </div>
      <div className="recurring-trend-legend">
        <span><i className="legend-swatch income" />Inkomsten</span>
        <span><i className="legend-swatch expense" />Kosten</span>
        <span><i className="legend-swatch net" />Netto</span>
      </div>
    </div>
  );
}

function RecurringCostRow({
  item,
  groups,
  isDragging,
  onMove,
  onDragStart,
  onDragEnd,
}: {
  item: RecurringCostInsight;
  groups: Array<{ id: RecurringCostGroupId; label: string }>;
  isDragging: boolean;
  onMove: (item: RecurringCostInsight, groupId: EditableRecurringCostGroupId) => void;
  onDragStart: () => void;
  onDragEnd: () => void;
}) {
  const editableGroups = groups.filter((group): group is { id: EditableRecurringCostGroupId; label: string } => group.id !== "income");
  const amount = item.direction === "income" ? item.monthlyEstimateCents : -item.lastAmountCents;
  return (
    <li
      className={isDragging ? "list-row recurring-cost-row dragging" : "list-row recurring-cost-row"}
      draggable={item.direction === "expense"}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
    >
      <div className="row-main">
        <div className="row-title">{item.title}</div>
        <div className="row-meta">
          {item.cadence} · {item.count} keer gezien · laatst {shortDate(item.lastDate)}
          {item.nextExpectedDate ? ` · verwacht ${shortDate(item.nextExpectedDate)}` : ""}
        </div>
        <div className="transaction-detail-tags">
          <span className="transaction-detail-tag"><strong>{item.direction === "income" ? "Basis" : "Gem."}</strong>{money(item.averageAmountCents)}</span>
          <span className="transaction-detail-tag"><strong>Maand</strong>{money(item.monthlyEstimateCents)}</span>
          {item.category && <span className="transaction-detail-tag"><strong>Cat.</strong>{item.category}</span>}
          <span className="transaction-detail-tag"><strong>Zekerheid</strong>{item.confidence}</span>
          {item.groupId && <span className="transaction-detail-tag"><strong>Groep</strong>Handmatig</span>}
          {item.forced && <span className="transaction-detail-tag"><strong>Bron</strong>Handmatig</span>}
        </div>
      </div>
      <div className="transaction-actions recurring-cost-actions">
        {item.direction === "expense" && (
          <select
            aria-label={`${item.title} verplaatsen naar groep`}
            className="compact-select"
            defaultValue={editableRecurringCostGroupId(item)}
            onChange={(event) => onMove(item, event.currentTarget.value as EditableRecurringCostGroupId)}
          >
            {editableGroups.map((group) => (
              <option key={group.id} value={group.id}>{group.label}</option>
            ))}
          </select>
        )}
        <span className={item.direction === "income" ? "status amount-status positive" : "status amount-status negative"}>{money(amount)}</span>
        <form action={setRecurringTransactionRule}>
          <input type="hidden" name="rule_key" value={item.key} />
          <input type="hidden" name="label" value={item.title} />
          <input type="hidden" name="rule_action" value="exclude_recurring" />
          <button className="button compact-button">Niet terugkerend</button>
        </form>
      </div>
    </li>
  );
}

function groupRecurringCosts(insights: RecurringCostInsight[], overrides: Record<string, EditableRecurringCostGroupId>) {
  return recurringCostGroupDefinitions
    .map((definition) => {
      const items = insights.filter((item) => (overrides[item.key] ?? recurringCostGroupId(item)) === definition.id);
      return {
        ...definition,
        items,
        totalCents: items.reduce((sum, item) => sum + item.monthlyEstimateCents, 0),
      };
    })
    .filter((group) => group.items.length > 0 || (group.id !== "income" && group.id !== "other"));
}

function recurringCostGroupId(item: RecurringCostInsight): RecurringCostGroupId {
  if (item.direction === "income") return "income";
  return editableRecurringCostGroupId(item);
}

function editableRecurringCostGroupId(item: RecurringCostInsight): EditableRecurringCostGroupId {
  if (isEditableRecurringCostGroupId(item.groupId)) return item.groupId;
  const text = `${item.title} ${item.category ?? ""}`.toLowerCase();
  if (matchesAny(text, ["belasting", "belastingdienst", "gemeente", "waterschap", "bsgr"])) return "tax";
  if (matchesAny(text, ["asr", "menzis", "verzekering", "verzekeraar", "zorgverzekering", "schadeverzekering"])) return "insurance";
  if (matchesAny(text, ["int card services", "card services", "ics", "credit", "krediet", "lening", "visa", "mastercard", "amex"])) return "credit";
  if (matchesAny(text, ["huur", "hypotheek", "stedelink", "energie", "water", "dunea", "vattenfall", "eneco", "essent", "gas", "elektra"])) return "fixed";
  if (item.category === "Abonnementen" || matchesAny(text, ["abonnement", "odido", "kpn", "ziggo", "vodafone", "netflix", "spotify", "apple", "disney", "videoland", "butternut", "zwemschool"])) return "subscription";
  return "other";
}

function isEditableRecurringCostGroupId(groupId: string | null): groupId is EditableRecurringCostGroupId {
  return groupId === "fixed" || groupId === "insurance" || groupId === "credit" || groupId === "subscription" || groupId === "tax" || groupId === "other";
}

function matchesAny(value: string, needles: string[]) {
  return needles.some((needle) => value.includes(needle));
}

async function saveRecurringGroup(item: RecurringCostInsight, groupId: EditableRecurringCostGroupId) {
  const response = await fetch("/api/finance/recurring-group", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rule_key: item.key,
      label: item.title,
      group_id: groupId,
    }),
  });
  if (!response.ok) throw new Error("Recurring cost group could not be saved.");
}
