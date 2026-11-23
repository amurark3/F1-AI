/**
 * The site's navigation, shared by the top bar, drawer, footer and homepage.
 */

export interface NavLink {
  href: string;
  label: string;
  /** Matches this path only, not the pages below it: the Command Center sits above every screen. */
  exact?: boolean;
  /** Other paths the link owns, so their pages light it too. */
  owns?: readonly string[];
  /** One line on what the screen holds, shown in the grouped menus. */
  description?: string;
}

export const COMMAND_CENTER_LINK = { href: "/race-control", label: "Race Control", exact: true } as const;
export const ENGINEER_LINK = { href: "/race-control/engineer", label: "AI Engineer" } as const;

type RaceNavLink = NavLink & { description: string; switcherLabel?: string; afterRace?: true };

export const RACE_VIEWS = {
  "grand-prix": {
    href: "/race-control/grand-prix",
    label: "Grand Prix",
    description: "Weekend, sessions, grid, results, predictions",
  },
  telemetry: {
    href: "/race-control/telemetry",
    label: "Telemetry",
    description: "Laps, speed traces and tyres",
  },
  debrief: {
    href: "/race-control/debriefs",
    label: "Debrief",
    description: "What happened in the race, and why",
    afterRace: true,
  },
  rewind: {
    href: "/race-control/rewind",
    label: "Race Rewind",
    description: "Replay the running order lap by lap",
    switcherLabel: "Rewind",
    afterRace: true,
  },
} as const satisfies Record<string, RaceNavLink>;

export type RaceView = keyof typeof RACE_VIEWS;
export const RACES = { id: "races", label: "Races", links: Object.values(RACE_VIEWS) } as const;

export const SEASON = {
  id: "season",
  label: "Season",
  links: [
    { href: "/race-control/standings", label: "Standings", description: "Championship gaps and who can still win" },
    {
      href: "/race-control/constructors",
      label: "Teams & drivers",
      description: "Line-ups and every driver's finishes",
      owns: ["/race-control/drivers"],
    },
    { href: "/race-control/power-units", label: "Power Units", description: "Engine allocations and grid penalties" },
  ],
} as const;

export const REFERENCE = {
  id: "reference",
  label: "Reference",
  links: [
    { href: "/race-control/champions", label: "Champions", description: "Every world champion since 1950" },
    { href: "/race-control/rulebook", label: "Rulebook", description: "Search the FIA regulations" },
  ],
} as const;

export const NAV_GROUPS = [RACES, SEASON, REFERENCE] as const;
export type NavGroup = (typeof NAV_GROUPS)[number];

export const NAV_LINKS: readonly NavLink[] = [
  COMMAND_CENTER_LINK,
  ...RACES.links,
  ...SEASON.links,
  ...REFERENCE.links,
  ENGINEER_LINK,
];

/** How the shell frames a route's content. */
export type ShellLayout = "bare" | "workspace" | "page";

/** Routes that fetch nothing at all, so the top bar's race status stays off there. */
const STATIC_ROUTES: readonly string[] = ["/"];

/** Routes that draw their own full-bleed layout under the bar. */
const BARE_ROUTES: readonly string[] = ["/"];

/**
 * Workspaces that fill the viewport under the bar and scroll inside
 * themselves, so they get no page wrap and no footer. Each prints the F1
 * disclaimer itself.
 */
const WORKSPACE_ROUTES: readonly string[] = [ENGINEER_LINK.href];

/** True when `pathname` is `path` or a page below it (whole segments only). */
function within(path: string, pathname: string): boolean {
  return pathname === path || pathname.startsWith(`${path}/`);
}

/**
 * Where `pathname` stands against a link: `page` on the link's own path,
 * `section` on a page below it or on a path it owns, otherwise null.
 */
export function currentState(link: NavLink, pathname: string): "page" | "section" | null {
  if (pathname === link.href) return "page";
  if (link.exact) return null;
  return [link.href, ...(link.owns ?? [])].some((path) => within(path, pathname)) ? "section" : null;
}

/** What `aria-current` says: "page" on the link's own page, "true" on a page in its section. */
const ARIA_CURRENT = { page: "page", section: "true" } as const;

/** The link's `aria-current`, or undefined when `pathname` is not in its section. */
export function ariaCurrent(link: NavLink, pathname: string): "page" | "true" | undefined {
  const state = currentState(link, pathname);
  return state === null ? undefined : ARIA_CURRENT[state];
}

/** How the shell frames `pathname`; an unknown path gets the page wrap. */
export function layoutFor(pathname: string): ShellLayout {
  if (BARE_ROUTES.includes(pathname)) return "bare";
  if (WORKSPACE_ROUTES.some((path) => within(path, pathname))) return "workspace";
  return "page";
}

/** The race status chip renders, and fetches, only on routes that read data. */
export function showsRaceStatus(pathname: string): boolean {
  return !STATIC_ROUTES.includes(pathname);
}
