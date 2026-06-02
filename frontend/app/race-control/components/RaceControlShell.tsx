"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import {
  BarChart3,
  Bot,
  BookOpenCheck,
  ClipboardList,
  Flag,
  Gauge,
  LayoutDashboard,
  Radio,
  Target,
  Users,
  ChevronRight,
} from "lucide-react";
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
      { href: "/race-control/strategy", label: "Strategy Lab", icon: Target },
      { href: "/race-control/predictions", label: "Championship Forecast", icon: Gauge },
      { href: "/race-control/teams", label: "Standings", icon: Users },
    ],
  },
  {
    label: "Reference",
    items: [
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
      if (diff <= 0) { setDisplay(null); return; }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setDisplay({
        label: next.label,
        countdown: h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`,
      });
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [sessions]);

  return display;
}

export default function RaceControlShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const contentRef = useRef<HTMLDivElement>(null);
  const year = new Date().getFullYear();

  const { data } = useSWR<SessionOverview>(
    `${API_BASE}/api/race-control/overview/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 120000 }
  );

  const nextSession = useNextSession(data?.race?.sessions ?? undefined);
  const isLive = data?.live_status?.connected === true;

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, left: 0 });
  }, [pathname]);

  const currentSection = ALL_NAV.find(({ href }) =>
    href === "/race-control" ? pathname === href : pathname.startsWith(href)
  );

  return (
    <main className="h-screen w-screen overflow-hidden bg-[#080A09] text-[15px] text-white">
      <div className="flex h-screen w-screen min-h-0">
        {/* Sidebar */}
        <aside className="hidden h-screen min-h-0 w-[232px] shrink-0 flex-col border-r border-white/[0.07] bg-[#0A0C0B] lg:flex">
          {/* Logo */}
          <div className="h-[60px] shrink-0 px-4 flex items-center gap-3 border-b border-white/[0.07]">
            <div className="h-8 w-8 rounded-lg border border-[#00FF78]/25 bg-[#00FF78]/8 flex items-center justify-center">
              <Gauge className="h-4 w-4 text-[#00FF78]" />
            </div>
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.22em] text-neutral-500">F1 AI</p>
              <p className="text-[15px] font-semibold uppercase leading-none text-white" style={rcHeaderFont}>
                Race Control
              </p>
            </div>
          </div>

          {/* Race context chip */}
          {data?.race && (
            <div className="mx-3 mt-3 rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2.5">
              <p className="text-[9px] font-black uppercase tracking-[0.2em] text-neutral-500 mb-0.5">Current Event</p>
              <p className="text-xs font-bold text-white leading-snug truncate">{data.race.name}</p>
              <div className="mt-1.5 flex items-center gap-1.5">
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: data.race.status === "in_progress" ? "#00FF78" : data.race.status === "upcoming" ? "#3671C6" : "#737373" }}
                />
                <p className="text-[10px] text-neutral-500 capitalize">{data.race.status.replace("_", " ")}</p>
              </div>
            </div>
          )}

          {/* Nav groups */}
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
                        className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[13px] transition-all border ${
                          active
                            ? "bg-white/[0.07] border-white/[0.08] text-white"
                            : "border-transparent text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.03]"
                        } focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#00FF78]/40`}
                      >
                        <Icon className="h-4 w-4 shrink-0" style={{ color: active ? "#00FF78" : undefined }} />
                        <span className="font-semibold">{label}</span>
                        {active && <ChevronRight className="ml-auto h-3 w-3 text-neutral-600" />}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* AI Engineer CTA */}
          <div className="shrink-0 p-3 border-t border-white/[0.06]">
            <Link
              href="/race-control/engineer"
              className="flex items-center gap-2.5 rounded-lg border border-[#00FF78]/20 bg-[#00FF78]/6 px-3 py-2.5 text-sm text-neutral-400 hover:text-neutral-100 hover:border-[#00FF78]/35 transition-all"
            >
              <Bot className="h-4 w-4 text-[#00FF78] shrink-0" />
              <span className="font-semibold text-[13px]">AI Engineer</span>
            </Link>
          </div>
        </aside>

        {/* Main content */}
        <section className="flex h-screen min-h-0 min-w-0 w-screen flex-1 flex-col lg:w-[calc(100vw-232px)]">
          {/* Header */}
          <header className="z-40 h-auto w-full shrink-0 border-b border-white/[0.07] bg-[#080A09]/95 backdrop-blur-xl">
            <div className="h-[60px] px-4 sm:px-5 flex items-center justify-between gap-4">
              {/* Mobile logo */}
              <Link href="/race-control" className="lg:hidden flex items-center gap-2">
                <Gauge className="h-4.5 w-4.5 text-[#00FF78]" />
                <span className="text-[15px] font-semibold uppercase leading-none" style={rcHeaderFont}>
                  Race Control
                </span>
              </Link>

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
                    <span className="text-[10px] font-black uppercase tracking-[0.14em] text-neutral-400">{nextSession.label}</span>
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
                  className="rounded-lg border border-white/[0.08] px-3 py-1.5 text-[13px] font-bold text-neutral-400 hover:text-white hover:bg-white/[0.04] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#00FF78]/40"
                >
                  <Radio className="inline h-3.5 w-3.5 mr-1.5" />
                  Engineer
                </Link>
              </div>
            </div>

            {/* Mobile nav scroll */}
            <nav className="lg:hidden px-4 pb-3 flex gap-1.5 overflow-x-auto scrollbar-none">
              {ALL_NAV.map(({ href, label }) => {
                const active = href === "/race-control" ? pathname === href : pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`shrink-0 rounded-lg px-3 py-2 text-[11px] font-black uppercase tracking-wider border ${
                      active ? "border-[#00FF78]/25 bg-[#00FF78]/8 text-white" : "border-white/[0.07] text-neutral-400"
                    } focus-visible:outline-none`}
                  >
                    {label}
                  </Link>
                );
              })}
            </nav>
          </header>

          <div ref={contentRef} className="min-h-0 w-full max-w-none flex-1 overflow-y-auto overscroll-contain">
            <div className="w-full max-w-none px-4 pt-7 pb-8 sm:px-6 sm:pt-8 sm:pb-10 [&>*]:w-full">
              {children}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
