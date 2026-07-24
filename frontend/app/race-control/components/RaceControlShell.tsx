"use client";

import {
  BarChart3,
  Bot,
  BookOpenCheck,
  ClipboardList,
  Flag,
  Gauge,
  LayoutDashboard,
  Radio,
  Trophy,
  Users,
  ChevronRight,
  Menu,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import SiteFooter from "@/app/components/SiteFooter";
import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";

const NAV_GROUPS = [
  {
    label: "Operations",
    items: [
      { href: "/race-control", label: "Command Center", icon: LayoutDashboard },
      { href: "/race-control/live", label: "Live Timing", icon: Radio },
      { href: "/race-control/engineer", label: "AI Engineer", icon: Bot },
    ],
  },
  {
    label: "Decision Tools",
    items: [
      { href: "/race-control/predictions", label: "Race Predictions", icon: Gauge },
      { href: "/race-control/teams", label: "Standings", icon: Users },
    ],
  },
  {
    label: "Reference",
    items: [
      { href: "/race-control/champions", label: "Champions", icon: Trophy },
      { href: "/race-control/intel", label: "Rival Intel", icon: BarChart3 },
      { href: "/race-control/debriefs", label: "Race Debriefs", icon: ClipboardList },
      { href: "/race-control/rulebook", label: "Rules Search", icon: BookOpenCheck },
    ],
  },
];

const ALL_NAV = NAV_GROUPS.flatMap((g) => g.items);

const rcHeaderFont = { fontFamily: "var(--font-geist-sans, Arial, Helvetica, sans-serif)" };

interface SessionOverview {
  race?: { name: string; status: string; sessions?: Record<string, string> } | null;
  live_status?: { connected: boolean; label: string };
}

const RACE_STATUS_COLORS: Record<string, string> = {
  in_progress: "#00FF78",
  upcoming: "#3671C6",
};
const RACE_STATUS_FALLBACK = "#737373";

/** Status dot colour for the current-event indicator. */
function raceStatusColor(status: string): string {
  return RACE_STATUS_COLORS[status] ?? RACE_STATUS_FALLBACK;
}

/** Formats a positive millisecond span as the coarsest useful countdown. */
function formatCountdown(h: number, m: number, s: number): string {
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function useNextSession(sessions?: Record<string, string>) {
  const [display, setDisplay] = useState<{ label: string; countdown: string } | null>(null);

  useEffect(() => {
    if (!sessions) return;

    const upcoming = Object.entries(sessions)
      .map(([label, iso]) => ({ label, time: new Date(iso).getTime() }))
      .filter((s) => s.time > Date.now())
      .sort((a, b) => a.time - b.time);

    const next = upcoming[0];
    if (!next) return;

    const tick = () => {
      const diff = next.time - Date.now();
      if (diff <= 0) {
        setDisplay(null);
        return;
      }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setDisplay({
        label: next.label,
        countdown: formatCountdown(h, m, s),
      });
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [sessions]);

  return display;
}

type RaceInfo = NonNullable<SessionOverview["race"]>;
type NavItem = (typeof ALL_NAV)[number];

/** "Current Event" chip shared by the desktop and mobile sidebars. */
function RaceContextChip({ race }: { race: RaceInfo }) {
  return (
    <div className="mx-3 mt-3 rounded-md border border-[#1E2633] bg-[#0D111B] px-3 py-2.5">
      <p className="mb-0.5 text-[9px] font-black uppercase tracking-[0.2em] text-neutral-500">Current Event</p>
      <p className="truncate text-xs font-bold leading-snug text-white">{race.name}</p>
      <div className="mt-1.5 flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: raceStatusColor(race.status) }} />
        <p className="text-[10px] capitalize text-neutral-500">{race.status.replace("_", " ")}</p>
      </div>
    </div>
  );
}

/** Grouped navigation list shared by both sidebars; `onNavigate` closes the mobile drawer. */
function SidebarNav({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3 space-y-4">
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          <p className="mb-1 px-2 text-[9px] font-black uppercase tracking-[0.22em] text-neutral-600">{group.label}</p>
          <div className="space-y-0.5">
            {group.items.map(({ href, label, icon: Icon }) => {
              const active = href === "/race-control" ? pathname === href : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={onNavigate}
                  className={`flex items-center gap-2.5 rounded-md border px-2.5 py-2.5 text-[13px] transition-all ${
                    active
                      ? "border-[#E10600]/35 bg-[#E10600]/12 text-white"
                      : "border-transparent text-neutral-400 hover:bg-white/[0.03] hover:text-neutral-200"
                  } focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#E10600]/40`}
                >
                  <Icon className="h-4 w-4 shrink-0" style={{ color: active ? "#FF4655" : undefined }} />
                  <span className="font-semibold">{label}</span>
                  {active && <ChevronRight className="ml-auto h-3 w-3 text-neutral-600" />}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

function DesktopSidebar({ pathname, race }: { pathname: string; race: RaceInfo | null }) {
  return (
    <aside className="hidden h-screen min-h-0 w-[232px] shrink-0 flex-col border-r border-[#1E2633] bg-[#080B11] lg:flex">
      {/* Logo — the way back out of the workspace to the landing page */}
      <Link
        href="/"
        aria-label="F1 AI home"
        className="h-[60px] shrink-0 px-4 flex items-center gap-3 border-b border-[#1E2633] transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#E10600]/40"
      >
        <div className="h-8 w-8 rounded-md border border-[#E10600]/35 bg-[#E10600]/15 flex items-center justify-center">
          <Gauge className="h-4 w-4 text-[#FF4655]" />
        </div>
        <div>
          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-neutral-500">F1 AI</p>
          <p className="text-[15px] font-semibold uppercase leading-none text-white" style={rcHeaderFont}>
            Race Control
          </p>
        </div>
      </Link>

      {race && <RaceContextChip race={race} />}

      <SidebarNav pathname={pathname} />

      {/* AI Engineer CTA */}
      <div className="shrink-0 p-3 border-t border-[#1E2633]">
        <Link
          href="/race-control/engineer"
          className="flex items-center gap-2.5 rounded-md border border-[#E10600]/25 bg-[#E10600]/10 px-3 py-2.5 text-sm text-neutral-400 hover:text-neutral-100 hover:border-[#E10600]/40 transition-all"
        >
          <Bot className="h-4 w-4 text-[#FF4655] shrink-0" />
          <span className="font-semibold text-[13px]">AI Engineer</span>
        </Link>
      </div>
    </aside>
  );
}

function MobileSidebar({
  pathname,
  race,
  navOpen,
  onClose,
}: {
  pathname: string;
  race: RaceInfo | null;
  navOpen: boolean;
  onClose: () => void;
}) {
  return (
    <aside
      className={`fixed inset-y-0 left-0 z-[60] flex w-[292px] max-w-[86vw] flex-col border-r border-[#1E2633] bg-[#080B11] transition-transform duration-200 lg:hidden ${
        navOpen ? "translate-x-0" : "-translate-x-full"
      }`}
      aria-label="Race Control navigation"
    >
      <div className="h-[60px] shrink-0 border-b border-[#1E2633] px-4 flex items-center justify-between gap-3">
        <Link
          href="/"
          onClick={onClose}
          aria-label="F1 AI home"
          className="flex min-w-0 items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#E10600]/40"
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[#E10600]/35 bg-[#E10600]/15">
            <Gauge className="h-4 w-4 text-[#FF4655]" />
          </div>
          <div className="min-w-0">
            <p className="text-[10px] font-black uppercase tracking-[0.22em] text-neutral-500">F1 AI</p>
            <p className="truncate text-[15px] font-semibold uppercase leading-none text-white" style={rcHeaderFont}>
              Race Control
            </p>
          </div>
        </Link>
        <button
          onClick={onClose}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[#1E2633] text-neutral-400 hover:bg-white/[0.04] hover:text-white"
          aria-label="Close navigation menu"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {race && <RaceContextChip race={race} />}

      <SidebarNav pathname={pathname} onNavigate={onClose} />
    </aside>
  );
}

interface ShellHeaderProps {
  currentSection?: NavItem;
  nextSession: { label: string; countdown: string } | null;
  isLive: boolean;
  onOpenNav: () => void;
}

function ShellHeader({ currentSection, nextSession, isLive, onOpenNav }: ShellHeaderProps) {
  return (
    <header className="z-40 h-auto w-full shrink-0 border-b border-[#1E2633] bg-[#080B11]/95 backdrop-blur-xl">
      <div className="h-[60px] px-4 sm:px-5 flex items-center justify-between gap-4">
        {/* Mobile menu + logo */}
        <div className="flex min-w-0 items-center gap-2 lg:hidden">
          <button
            onClick={onOpenNav}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-[#1E2633] text-neutral-300 hover:bg-white/[0.04] hover:text-white"
            aria-label="Open navigation menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <Link href="/" aria-label="F1 AI home" className="flex min-w-0 items-center gap-2">
            <Gauge className="h-4.5 w-4.5 shrink-0 text-[#FF4655]" />
            <span className="truncate text-[15px] font-semibold uppercase leading-none" style={rcHeaderFont}>
              Race Control
            </span>
          </Link>
        </div>

        {/* Desktop breadcrumb */}
        <div className="hidden lg:flex items-center gap-2 min-w-0">
          <Flag className="h-3.5 w-3.5 text-neutral-600 shrink-0" />
          <span className="text-[11px] font-bold uppercase tracking-[0.18em] text-neutral-500">Race Control</span>
          {currentSection && (
            <>
              <ChevronRight className="h-3 w-3 text-neutral-700 shrink-0" />
              <span className="text-[11px] font-bold uppercase tracking-[0.18em] text-neutral-300 truncate">
                {currentSection.label}
              </span>
            </>
          )}
        </div>

        {/* Right side: session countdown + live indicator + engineer link */}
        <div className="flex items-center gap-2 shrink-0">
          {nextSession && (
            <div className="hidden sm:flex items-center gap-2 rounded border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-[#3671C6] shrink-0" />
              <span className="text-[10px] font-black uppercase tracking-[0.14em] text-neutral-400">
                {nextSession.label}
              </span>
              <span className="font-mono text-[10px] font-bold text-white">{nextSession.countdown}</span>
            </div>
          )}

          {isLive && (
            <span className="hidden sm:inline-flex items-center gap-1.5 rounded border border-[#E10600]/30 bg-[#E10600]/8 px-2.5 py-1.5 text-[10px] font-black uppercase tracking-[0.14em] text-[#E10600]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#E10600] animate-pulse" />
              Live
            </span>
          )}

          {!isLive && !nextSession && (
            <span className="hidden sm:inline-flex items-center gap-1.5 rounded border border-white/[0.07] px-2.5 py-1.5 text-[10px] font-black uppercase tracking-[0.14em] text-neutral-500">
              <span className="h-1.5 w-1.5 rounded-full bg-neutral-600" />
              Standby
            </span>
          )}

          <Link
            href="/race-control/engineer"
            className="rounded-md border border-[#1E2633] px-3 py-1.5 text-[13px] font-bold text-neutral-400 hover:text-white hover:bg-white/[0.04] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#E10600]/40"
          >
            <Radio className="inline h-3.5 w-3.5 mr-1.5" />
            Engineer
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function RaceControlShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const contentRef = useRef<HTMLDivElement>(null);
  const [navOpen, setNavOpen] = useState(false);
  const year = new Date().getFullYear();

  const { data } = useSWR<SessionOverview>(`${API_BASE}/api/race-control/overview/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 120000,
  });

  const nextSession = useNextSession(data?.race?.sessions ?? undefined);
  const isLive = data?.live_status?.connected === true;
  const race = data?.race ?? null;

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, left: 0 });
  }, [pathname]);

  const currentSection = ALL_NAV.find(({ href }) =>
    href === "/race-control" ? pathname === href : pathname.startsWith(href),
  );

  return (
    <main className="h-screen w-screen overflow-hidden bg-[#07090D] text-[15px] text-white">
      <div className="flex h-screen w-screen min-h-0">
        <DesktopSidebar pathname={pathname} race={race} />

        {navOpen && (
          <button
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm lg:hidden"
            onClick={() => setNavOpen(false)}
            aria-label="Close navigation menu"
          />
        )}

        <MobileSidebar pathname={pathname} race={race} navOpen={navOpen} onClose={() => setNavOpen(false)} />

        {/* Main content */}
        <section className="flex h-screen min-h-0 min-w-0 w-screen flex-1 flex-col lg:w-[calc(100vw-232px)]">
          <ShellHeader
            currentSection={currentSection}
            nextSession={nextSession}
            isLive={isLive}
            onOpenNav={() => setNavOpen(true)}
          />

          <div ref={contentRef} className="min-h-0 w-full max-w-none flex-1 overflow-y-auto overscroll-contain">
            <div className="w-full max-w-none px-4 pt-7 pb-8 sm:px-6 sm:pt-8 sm:pb-10 [&>*]:w-full">{children}</div>
            {/* Lives inside the scroll container — the shell itself is fixed to the viewport. */}
            <SiteFooter compact />
          </div>
        </section>
      </div>
    </main>
  );
}
