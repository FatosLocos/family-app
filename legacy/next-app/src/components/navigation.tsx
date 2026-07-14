"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  Banknote,
  Bell,
  BookUser,
  CalendarDays,
  CalendarRange,
  CheckSquare,
  Database,
  FileText,
  Gift,
  House,
  Home,
  LayoutDashboard,
  ListChecks,
  MessageSquare,
  Plus,
  Plug,
  Repeat2,
  Search,
  Settings,
  ShieldAlert,
  ShoppingBasket,
  Sun,
  UsersRound,
  Wrench,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type NavGroup = "Start" | "Dagelijks" | "Planning" | "Huis" | "Beheer";

const nav: Array<{
  label: string;
  href: string;
  group: NavGroup;
  description: string;
  primary?: boolean;
  icon?: LucideIcon;
}> = [
  { label: "Dashboard", href: "/", group: "Start", description: "Compact gezinsdashboard met alle signalen bij elkaar.", icon: LayoutDashboard },
  { label: "Vandaag", href: "/vandaag", group: "Start", description: "Dagbeeld met taken, afspraken, eten en boodschappen.", primary: true, icon: Sun },
  { label: "Week", href: "/week", group: "Start", description: "Planning en aandachtspunten voor de komende zeven dagen.", primary: true, icon: CalendarRange },
  { label: "Activiteit", href: "/activiteit", group: "Start", description: "Tijdlijn van recente en aankomende gezinsgebeurtenissen.", icon: Activity },
  { label: "Meldingen", href: "/meldingen", group: "Start", description: "Centrale inbox voor herinneringen uit alle modules.", primary: true, icon: Bell },
  { label: "Zoeken", href: "/zoeken", group: "Start", description: "Vind gegevens terug over taken, geld, agenda en huiszaken.", icon: Search },
  { label: "Snel", href: "/snel", group: "Start", description: "Leg direct een taak, boodschap, notitie of gelditem vast.", primary: true, icon: Plus },
  { label: "Wie doet wat", href: "/wie-doet-wat", group: "Dagelijks", description: "Verdeling van taken en afspraken per gezinslid.", icon: UsersRound },
  { label: "Prikbord", href: "/prikbord", group: "Dagelijks", description: "Korte gezinsberichten en vastgezette mededelingen.", icon: MessageSquare },
  { label: "Taken", href: "/taken", group: "Dagelijks", description: "Taken, subtaken, deadlines, herhaling en verdeling.", primary: true, icon: CheckSquare },
  { label: "Boodschappen", href: "/boodschappen", group: "Dagelijks", description: "Lijst, prijzen, maaltijden en bonnen in een hoofdcategorie.", primary: true, icon: ShoppingBasket },
  { label: "Wishlist", href: "/wishlist", group: "Dagelijks", description: "Verlanglijst met externe deel-link en afstreepfunctie.", primary: true, icon: Gift },
  { label: "Routines", href: "/routines", group: "Dagelijks", description: "Terugkerende taken, producten en onderhoud op een plek.", icon: Repeat2 },
  { label: "Agenda", href: "/agenda", group: "Planning", description: "Gezinsagenda met handmatige afspraken en Outlook-koppeling.", primary: true, icon: CalendarDays },
  { label: "Geld", href: "/geld", group: "Planning", description: "Vaste lasten, budgetten, bankkoppeling en betaalmomenten.", primary: true, icon: Banknote },
  { label: "Gezin", href: "/gezin", group: "Huis", description: "Gezinsleden, contacten en belangrijke huisinformatie.", icon: UsersRound },
  { label: "Adresboek", href: "/adresboek", group: "Huis", description: "Familie, vrienden, adressen en verjaardagen centraal beheren.", icon: BookUser },
  { label: "Noodkaart", href: "/noodkaart", group: "Huis", description: "Noodcontacten, belangrijke documenten en huisinstructies.", icon: ShieldAlert },
  { label: "Documenten", href: "/documenten", group: "Huis", description: "Documentkluis met locaties, referenties en vervaldatums.", icon: FileText },
  { label: "Onderhoud", href: "/onderhoud", group: "Huis", description: "Onderhoudsplanning voor huis, techniek, tuin en veiligheid.", icon: Wrench },
  { label: "Home", href: "/home", group: "Huis", description: "Smart home bediening voor Hue, Home Assistant en Google Home.", primary: true, icon: House },
  { label: "Koppelingen", href: "/koppelingen", group: "Beheer", description: "Status en beheer van externe integraties.", icon: Plug },
  { label: "Inrichting", href: "/inrichting", group: "Beheer", description: "Checklist om de gezinsapp volledig in te richten.", icon: Settings },
  { label: "Data", href: "/data", group: "Beheer", description: "Opslag, privacy en export van gezinsdata.", icon: Database },
  { label: "Instellingen", href: "/instellingen", group: "Beheer", description: "Huishouden, voorkeuren, sessies en uitnodigingen." },
];

const groupNav: Array<{
  group: NavGroup;
  href: string;
  description: string;
  icon: LucideIcon;
}> = [
  { group: "Start", href: "/vandaag", description: "Overzicht", icon: Home },
  { group: "Dagelijks", href: "/taken", description: "Dagelijks", icon: ListChecks },
  { group: "Planning", href: "/agenda", description: "Planning", icon: CalendarDays },
  { group: "Huis", href: "/gezin", description: "Huis", icon: House },
  { group: "Beheer", href: "/instellingen", description: "Beheer", icon: Settings },
];

export function MainNavigation() {
  const pathname = usePathname();
  const current = currentNavItem(pathname);
  const [openGroup, setOpenGroup] = useState<NavGroup | null>(null);

  useEffect(() => {
    setOpenGroup(null);
  }, [pathname]);

  return (
    <nav className="nav" aria-label="Hoofdnavigatie" onKeyDown={(event) => {
      if (event.key === "Escape") setOpenGroup(null);
    }}>
      {groupNav.map(({ group, icon: Icon }) => {
        const active = current.group === group;
        const siblingItems = nav.filter((item) => item.group === group);
        const open = openGroup === group;
        return (
          <div className="nav-speed-group" data-open={open ? "true" : undefined} key={group} onMouseEnter={() => setOpenGroup(group)} onMouseLeave={() => setOpenGroup(null)}>
            <button
              className="nav-main-link"
              type="button"
              title={group}
              aria-label={`${group} openen`}
              aria-current={active ? "page" : undefined}
              aria-expanded={open}
              aria-haspopup="menu"
              data-active={active ? "true" : undefined}
              onClick={() => setOpenGroup((currentOpen) => currentOpen === group ? null : group)}
              onFocus={() => setOpenGroup(group)}
            >
              <Icon size={18} strokeWidth={2.25} />
              <span className="sr-only">{group}</span>
            </button>
            <div className="nav-speed-dial" aria-label={`${group} submenu`} role="menu">
              <div className="nav-speed-links">
                {siblingItems.map((item) => {
                  const itemActive = isActivePath(pathname, item.href);
                  const ItemIcon = item.icon;
                  return (
                    <Link key={item.href} href={item.href} aria-current={itemActive ? "page" : undefined} data-active={itemActive ? "true" : undefined} role="menuitem">
                      {ItemIcon && <ItemIcon size={14} />}
                      <span>{item.label}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })}
    </nav>
  );
}

export function MobileTabBar() {
  const pathname = usePathname();
  const current = currentNavItem(pathname);
  const [openGroup, setOpenGroup] = useState<NavGroup | null>(null);

  useEffect(() => {
    setOpenGroup(null);
  }, [pathname]);

  return (
    <nav className="mobile-tabbar" aria-label="Hoofdnavigatie mobiel" onKeyDown={(event) => {
      if (event.key === "Escape") setOpenGroup(null);
    }}>
      {groupNav.map(({ group, icon: Icon }) => {
        const siblingItems = nav.filter((item) => item.group === group);
        const active = current.group === group;
        const open = openGroup === group;
        return (
          <div className="mobile-nav-group" data-open={open ? "true" : undefined} key={group}>
            <button
              type="button"
              aria-label={`${group} openen`}
              aria-current={active ? "page" : undefined}
              aria-expanded={open}
              aria-haspopup="menu"
              data-active={active ? "true" : undefined}
              onClick={() => setOpenGroup((currentOpen) => currentOpen === group ? null : group)}
            >
              <Icon size={18} />
              <span>{group}</span>
            </button>
            {open && (
              <>
                <button className="mobile-speed-backdrop" type="button" aria-label="Menu sluiten" onClick={() => setOpenGroup(null)} />
                <div className="mobile-speed-dial" role="menu" aria-label={`${group} submenu`}>
                  <div className="mobile-speed-head">
                    <strong>{group}</strong>
                    <button type="button" aria-label={`${group} sluiten`} title="Sluiten" onClick={() => setOpenGroup(null)}><X size={16} /></button>
                  </div>
                  <div className="mobile-speed-links">
                    {siblingItems.map((item) => {
                      const itemActive = isActivePath(pathname, item.href);
                      const ItemIcon = item.icon;
                      return (
                        <Link key={item.href} href={item.href} data-active={itemActive ? "true" : undefined} role="menuitem">
                          {ItemIcon && <ItemIcon size={16} />}
                          <span>{item.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              </>
            )}
          </div>
        );
      })}
    </nav>
  );
}

function isActivePath(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function currentNavItem(pathname: string) {
  return [...nav]
    .sort((a, b) => b.href.length - a.href.length)
    .find((item) => isActivePath(pathname, item.href)) ?? nav[0];
}
