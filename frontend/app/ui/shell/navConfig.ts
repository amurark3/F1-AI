/**
 * The site's navigation, in one place: the top bar's links, the screens kept
 * under "More", and which routes the shell frames how. No React, so the
 * header, the mobile menu and (P3.4) the footer all read the same lists.
 */

export interface NavLink {
  href: string;
  label: string;
  /** Matches this path only, not the pages below it: the Command Center sits above every screen. */
  exact?: boolean;
  /** Other paths the link owns, so their pages light it too. */
  owns?: readonly string[];
  /** One line on what the screen holds, shown in the More menu. */
  description?: string;
}

/** The top bar, left to right (docs/design/redesign: every mockup's `.nav`). */
export const PRIMARY_NAV: readonly NavLink[] = [
  { href: "/race-control", label: "Race Control", exact: true },
  { href: "/race-control/grand-prix", label: "Grand Prix" },
  { href: "/race-control/telemetry", label: "Telemetry" },
  { href: "/race-control/teams", label: "Standings" },
  { href: "/race-control/constructors", label: "Teams", owns: ["/race-control/drivers"] },
  { href: "/race-control/power-units", label: "Power Units" },
  { href: "/race-control/engineer", label: "AI Engineer" },
];

/** The reference screens behind the "More" menu (PLAN, Locked decisions: Navigation). */
export const MORE_NAV: readonly NavLink[] = [
  { href: "/race-control/champions", label: "Champions", description: "Every world champion since 1950" },
  { href: "/race-control/debriefs", label: "Debriefs", description: "What happened in each race, and why" },
  { href: "/race-control/rulebook", label: "Rulebook", description: "Search the FIA regulations" },
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
const WORKSPACE_ROUTES: readonly string[] = ["/race-control/engineer"];

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

/** True on any screen kept under "More", so its trigger shows the current section. */
export function isMoreCurrent(pathname: string): boolean {
  return MORE_NAV.some((link) => currentState(link, pathname) !== null);
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
