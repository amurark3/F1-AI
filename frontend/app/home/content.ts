/**
 * The homepage's copy and links (docs/design/redesign/home.html).
 *
 * Static on purpose (PLAN, Locked decisions: Homepage): no names, results,
 * dates or counts that could go stale or wrong between deploys. Every href is
 * a screen in `ui/shell/navConfig.ts`; `app/page.test.tsx` holds them to it.
 */

export interface HomeLink {
  href: string;
  title: string;
  description: string;
}

/** The two ways in under the hero's headline. */
export const HERO_CTAS = {
  primary: { href: "/race-control", label: "Enter Race Control" },
  secondary: { href: "/race-control/engineer", label: "Ask the AI Engineer" },
} as const;

/** 01 · Race weekend: the two screens a weekend runs on. */
export const COMMAND_CENTER: HomeLink & { eyebrow: string } = {
  href: "/race-control",
  eyebrow: "Command Center",
  title: "This weekend, on one screen",
  description:
    "Session-by-session forecast, what the title fight hinges on, the strategy baseline and the model's podium.",
};

export const AI_ENGINEER: HomeLink & { eyebrow: string; questions: readonly string[] } = {
  href: "/race-control/engineer",
  eyebrow: "AI Engineer",
  title: "Ask anything",
  description:
    "Strategy, history or the regulations, in plain English. Answers come from the same results database the screens use.",
  // One of each kind it answers. Questions only: a sample answer would be baked-in data.
  questions: [
    "Why do teams pit under a safety car?",
    "What does the rulebook say about track limits?",
    "Who has won the most races from pole?",
  ],
};

/** Which data-free motif heads a decision-tool card. */
export type ToolMotif = "calendar" | "traces" | "standings" | "lineups" | "powerUnits";

/** 02 · Decision tools: three cards, then two wide ones. */
export const TOOLS: ReadonlyArray<HomeLink & { motif: ToolMotif; wide?: boolean }> = [
  {
    href: "/race-control/grand-prix",
    title: "Grand Prix Hub",
    description: "Every round: sessions, grid, tyre stints and the model's call.",
    motif: "calendar",
  },
  {
    href: "/race-control/telemetry",
    title: "Telemetry Lab",
    description: "Speed maps, head-to-head laps and tyre degradation since 2023.",
    motif: "traces",
  },
  {
    href: "/race-control/teams",
    title: "Standings",
    description: "Both championships, and how the gap moved race by race.",
    motif: "standings",
  },
  {
    href: "/race-control/constructors",
    title: "Teams & Drivers",
    description: "Line-ups, wins and every driver's finish in every round.",
    motif: "lineups",
    wide: true,
  },
  {
    href: "/race-control/power-units",
    title: "Power Units",
    description: "Engine allocations per car, and the grid penalties they cost.",
    motif: "powerUnits",
    wide: true,
  },
];

/** 03 · Reference: dense rows, a change of pace. */
export const REFERENCE: readonly HomeLink[] = [
  {
    href: "/race-control/champions",
    title: "Champions",
    description: "Every drivers' and constructors' title since 1950.",
  },
  { href: "/race-control/debriefs", title: "Race Debriefs", description: "What happened in each race, and why." },
  { href: "/race-control/rulebook", title: "Rulebook", description: "Search the FIA regulations by meaning." },
];
