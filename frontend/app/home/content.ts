import { COMMAND_CENTER_LINK, ENGINEER_LINK, RACES, REFERENCE, SEASON } from "@/app/ui/shell/navConfig";

export interface HomeLink {
  href: string;
  title: string;
  description: string;
}

/** The two ways in under the hero's headline. */
export const HERO_CTAS = {
  primary: { href: COMMAND_CENTER_LINK.href, label: "Enter Race Control" },
  secondary: { href: ENGINEER_LINK.href, label: "Ask the AI Engineer" },
} as const;

export const COMMAND_CENTER: HomeLink & { eyebrow: string } = {
  href: COMMAND_CENTER_LINK.href,
  eyebrow: "Command Center",
  title: "This weekend, on one screen",
  description:
    "Session-by-session forecast, what the title fight hinges on, the strategy baseline and the model's podium.",
};

export const AI_ENGINEER: HomeLink & { questions: readonly string[] } = {
  href: ENGINEER_LINK.href,
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

interface ToolCopy {
  motif: ToolMotif;
  description: string;
}
export type ToolMotif =
  "calendar" | "leaders" | "rewind" | "traces" | "standings" | "lineups" | "powerUnits" | "podium" | "regulations";

const RACE_COPY: Record<(typeof RACES.links)[number]["href"], ToolCopy> = {
  "/race-control/grand-prix": {
    description: "Every round: sessions, grid, results and the model's call.",
    motif: "calendar",
  },
  "/race-control/debriefs": {
    description: "What happened in the race, and why: leaders, stops, penalties.",
    motif: "leaders",
  },
  "/race-control/rewind": {
    description: "Replay the running order lap by lap, every change explained.",
    motif: "rewind",
  },
  "/race-control/telemetry": {
    description: "Speed maps, head-to-head laps and tyre degradation since 2023.",
    motif: "traces",
  },
};

const SEASON_COPY: Record<(typeof SEASON.links)[number]["href"], ToolCopy> = {
  "/race-control/standings": {
    description: "Both championships, how the gap moved, and who can still win.",
    motif: "standings",
  },
  "/race-control/constructors": {
    description: "Line-ups, wins and every driver's finish in every round.",
    motif: "lineups",
  },
  "/race-control/power-units": {
    description: "Engine allocations per car, and the grid penalties they cost.",
    motif: "powerUnits",
  },
};

const REFERENCE_COPY: Record<(typeof REFERENCE.links)[number]["href"], ToolCopy> = {
  "/race-control/champions": {
    description: "Every drivers' and constructors' title since 1950.",
    motif: "podium",
  },
  "/race-control/rulebook": {
    description: "Search the FIA regulations by meaning.",
    motif: "regulations",
  },
};

export const RACE_CARDS = RACES.links.map(({ href, label }) => ({ href, title: label, ...RACE_COPY[href] }));
export const SEASON_CARDS = SEASON.links.map(({ href, label }) => ({ href, title: label, ...SEASON_COPY[href] }));
export const REFERENCE_CARDS = REFERENCE.links.map(({ href, label }) => ({
  href,
  title: label,
  ...REFERENCE_COPY[href],
}));
