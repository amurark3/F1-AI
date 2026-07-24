import {
  ArrowRight,
  BarChart3,
  Bot,
  BookOpenCheck,
  ClipboardList,
  Gauge,
  LayoutDashboard,
  Radio,
  Trophy,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

/**
 * Landing page.
 *
 * Deliberately static — it fetches nothing, so it renders the instant the
 * frontend loads even while the Render backend is still spinning up from idle.
 * The readiness probe in the root layout runs underneath it, which both wakes the
 * container and reports progress in the warming banner. By the time a visitor
 * picks a workspace, the server has usually finished warming.
 *
 * Adding a data dependency here would defeat the point.
 */

const rcMono = { fontFamily: "var(--font-geist-mono, var(--font-geist-sans, monospace))" };
const rcFont = { fontFamily: "var(--font-geist-sans, Arial, Helvetica, sans-serif)" };

interface Workspace {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

interface WorkspaceGroup {
  label: string;
  accent: string;
  items: readonly Workspace[];
}

const WORKSPACE_GROUPS: readonly WorkspaceGroup[] = [
  {
    label: "Operations",
    accent: "#E10600",
    items: [
      {
        href: "/race-control",
        label: "Command Center",
        description: "Race weekend overview — session timing, championship pressure, and the strategy baseline.",
        icon: LayoutDashboard,
      },
      {
        href: "/race-control/live",
        label: "Live Timing",
        description: "Timing tower, sector deltas, and session commentary while a session is running.",
        icon: Radio,
      },
      {
        href: "/race-control/engineer",
        label: "AI Engineer",
        description: "Ask about strategy, history, or the regulations in plain English.",
        icon: Bot,
      },
    ],
  },
  {
    label: "Decision Tools",
    accent: "#00FF78",
    items: [
      {
        href: "/race-control/predictions",
        label: "Race Predictions",
        description: "Model-ranked finishing order, with the reasoning behind each driver's placement.",
        icon: Gauge,
      },
      {
        href: "/race-control/teams",
        label: "Standings",
        description: "Drivers' and constructors' championship tables for the current season.",
        icon: Users,
      },
    ],
  },
  {
    label: "Reference",
    accent: "#3671C6",
    items: [
      {
        href: "/race-control/champions",
        label: "Champions",
        description: "Every title winner from 1950 to the present, drivers and constructors.",
        icon: Trophy,
      },
      {
        href: "/race-control/intel",
        label: "Rival Intel",
        description: "Head-to-head pace comparisons and competitor threat analysis.",
        icon: BarChart3,
      },
      {
        href: "/race-control/debriefs",
        label: "Race Debriefs",
        description: "Post-race breakdowns of what actually happened and why.",
        icon: ClipboardList,
      },
      {
        href: "/race-control/rulebook",
        label: "Rules Search",
        description: "Search the FIA regulations by meaning rather than exact wording.",
        icon: BookOpenCheck,
      },
    ],
  },
];

function WorkspaceCard({ href, label, description, icon: Icon, accent }: Workspace & { accent: string }) {
  return (
    <Link
      href={href}
      className="group flex min-w-0 flex-col rounded-md border border-[#1E2633] bg-[#0D111B] p-5 transition-colors hover:border-white/20 hover:bg-[#101520] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#E10600]/40"
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border"
          style={{ borderColor: `${accent}40`, background: `${accent}14` }}
        >
          <Icon className="h-4 w-4" style={{ color: accent }} />
        </div>
        <ArrowRight className="h-4 w-4 shrink-0 text-neutral-700 transition-all group-hover:translate-x-0.5 group-hover:text-neutral-400" />
      </div>
      <p className="text-[15px] font-semibold text-white" style={rcFont}>
        {label}
      </p>
      <p className="mt-1.5 text-sm leading-relaxed text-[#8E96A8]">{description}</p>
    </Link>
  );
}

export default function HomePage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 pb-16 pt-10 sm:px-6 sm:pt-14">
      {/* Hero */}
      <section className="border-b border-[#1E2633] pb-10">
        <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.24em] text-[#7F8797]" style={rcMono}>
          Formula 1 Race Intelligence
        </p>
        <h1
          className="max-w-3xl text-4xl font-black uppercase italic leading-[0.95] tracking-tighter text-white sm:text-6xl"
          style={rcFont}
        >
          Your AI
          <span className="ml-3" style={{ color: "#E10600" }}>
            Race Engineer
          </span>
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-relaxed text-[#8E96A8]">
          Live timing, championship context, and a prediction model trained on seven decades of race
          results — with an assistant that can explain any of it on request.
        </p>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Link
            href="/race-control"
            className="inline-flex items-center gap-2 rounded-md border border-[#E10600]/40 bg-[#E10600]/12 px-4 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-[#E10600]/20 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#E10600]/40"
          >
            Enter Race Control
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href="/race-control/engineer"
            className="inline-flex items-center gap-2 rounded-md border border-[#1E2633] px-4 py-2.5 text-[13px] font-bold text-neutral-300 transition-colors hover:border-white/20 hover:bg-white/[0.04] hover:text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#E10600]/40"
          >
            <Bot className="h-4 w-4" />
            Ask the AI Engineer
          </Link>
        </div>
      </section>

      {/* Workspaces */}
      <section className="mt-10 space-y-9">
        {WORKSPACE_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="mb-4 flex items-center gap-3">
              <span className="h-[2px] w-6 shrink-0" style={{ background: group.accent }} />
              <p
                className="text-[10px] font-black uppercase tracking-[0.22em] text-[#7F8797]"
                style={rcMono}
              >
                {group.label}
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {group.items.map((item) => (
                <WorkspaceCard key={item.href} {...item} accent={group.accent} />
              ))}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
