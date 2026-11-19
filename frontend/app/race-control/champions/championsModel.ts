import { FIRST_SEASON } from "@/app/lib/server/champions";
import type { Age, LatestChampion, SeasonChampion, TitleEntry } from "@/app/lib/server/champions";
import { driverLabel } from "@/app/ui/names/names";

export type TitleState = "open" | "clinched" | "final";

export interface HeroFact {
  value: string;
  caption: string;
}

export interface HeroCopy {
  eyebrow: string;
  title: string;
  meta: string;
  facts: HeroFact[];
}

export interface Decade {
  label: string;
  seasons: SeasonChampion[];
}

const ORDINAL_SUFFIX: Record<string, string> = { one: "st", two: "nd", few: "rd", other: "th" };
const ORDINALS = new Intl.PluralRules("en", { type: "ordinal" });
const NAMES = new Intl.ListFormat("en", { type: "conjunction" });

/** 1 -> "1st", 22 -> "22nd", 11 -> "11th". */
export function ordinal(n: number): string {
  return `${n}${ORDINAL_SUFFIX[ORDINALS.select(n)]}`;
}

/** "20 y 68 d". */
export function formatAge({ years, days }: Age): string {
  return `${years} y ${days} d`;
}

/** "after round 20 of 23". */
export function afterRound(s: { rounds_completed: number; round_count: number }): string {
  return `after round ${s.rounds_completed} of ${s.round_count}`;
}

/** "3 rounds still to run". */
export function stillToRun(n: number): string {
  return `${n} ${n === 1 ? "round" : "rounds"} still to run`;
}

/** Open until the drivers' title is decided; a decided title is clinched while rounds remain, else final. */
export function titleState(s: SeasonChampion): TitleState {
  if (!s.driver_champion?.title_decided) return "open";
  return s.rounds_completed < s.round_count ? "clinched" : "final";
}

function ageFact(latest: LatestChampion): HeroFact | null {
  if (!latest.age) return null;
  const value = formatAge(latest.age);
  const prev = latest.previous_youngest;
  if (!prev) return { value, caption: "Age when the title was decided" };
  const last = driverLabel({ name: prev.name, lastName: prev.last_name }, "last");
  const record = `${last} was ${formatAge(prev.age)} in ${prev.season}`;
  if (latest.youngest_ever) return { value, caption: `Youngest champion ever · ${record}` };
  return {
    value,
    caption: `Age when the title was decided · the record is ${last}'s ${formatAge(prev.age)} in ${prev.season}`,
  };
}

function nationalityFact(latest: LatestChampion): HeroFact | null {
  const { nationality, previous_compatriot: c } = latest;
  if (!nationality) return null;
  if (c) return { value: `${c.season}`, caption: `${nationality}'s last champion before him · ${c.name}` };
  return { value: "1st", caption: `World Champion from ${nationality}` };
}

/** Every line of the hero, computed from the latest champion's record. */
export function heroCopy(latest: LatestChampion): HeroCopy {
  const identity = { name: latest.name, lastName: latest.last_name };
  const full = driverLabel(identity, "full");
  const last = driverLabel(identity, "last");
  const first = latest.title_number === 1;
  const left = latest.round_count - latest.rounds_completed;
  const place = latest.decided_at?.place;
  const different = first ? `, the ${ordinal(latest.champion_number)} different driver to become World Champion` : "";
  const meta = `${full} clinched the ${latest.season} title${place ? ` in ${place}` : ""}${different}.${
    left > 0 ? ` ${stillToRun(left)}.` : ""
  }`;
  const numberFact: HeroFact = first
    ? { value: ordinal(latest.champion_number), caption: `different World Champion since ${FIRST_SEASON}` }
    : { value: ordinal(latest.title_number), caption: `World title for ${last}` };

  return {
    eyebrow: `World Champions · ${FIRST_SEASON}–${latest.season}`,
    title: first ? `${last} joins the list` : `${last} makes it ${latest.title_number}`,
    meta,
    facts: [ageFact(latest), nationalityFact(latest), numberFact].filter((fact): fact is HeroFact => fact !== null),
  };
}

/** The top `rows`, widened so a tie at the cut stays whole. */
export function leaders(entries: TitleEntry[], rows = 8): TitleEntry[] {
  const cut = (entries[rows - 1] ?? entries.at(-1))?.titles;
  return cut === undefined ? [] : entries.filter((e) => e.titles >= cut);
}

/** A card's finding: "Hamilton and Schumacher, 7 each", "Ferrari lead with 16". */
export function leaderboardTitle(entries: TitleEntry[], kind: "drivers" | "constructors"): string | null {
  const top = entries[0]?.titles;
  if (top === undefined) return null;
  const names = entries
    .filter((e) => e.titles === top)
    .map((e) => (kind === "drivers" ? driverLabel({ name: e.name, lastName: e.last_name }, "last") : e.name));
  if (names.length === 1) return `${names[0]} ${kind === "drivers" ? "leads" : "lead"} with ${top}`;
  return `${NAMES.format(names)}, ${top} each`;
}

/** Seasons grouped by decade, newest decade first; within a decade oldest first, so columns line up by last digit. */
export function decades(seasons: SeasonChampion[]): Decade[] {
  const groups = new Map<number, SeasonChampion[]>();
  for (const s of seasons) {
    const start = Math.floor(s.season / 10) * 10;
    groups.set(start, [...(groups.get(start) ?? []), s]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => b - a)
    .map(([start, list]) => ({ label: `${start}s`, seasons: [...list].sort((a, b) => a.season - b.season) }));
}

/** A wall cell's accessible name. */
export function cellLabel(s: SeasonChampion): string {
  const driver = s.driver_champion;
  if (!driver?.title_decided) return `${s.season}: title still open`;
  const full = driverLabel({ name: driver.name, lastName: driver.last_name }, "full");
  const constructor = s.constructor_champion?.title_decided
    ? `, constructors' champion ${s.constructor_champion.name}`
    : "";
  const clinched =
    titleState(s) === "clinched" ? `, clinched with ${stillToRun(s.round_count - s.rounds_completed)}` : "";
  return `${s.season}: ${full}${constructor}${clinched}`;
}

/** The wall's footer: the source, every season still running, and when constructors' titles began. */
export function sourceNote(seasons: SeasonChampion[]): string {
  const running = seasons
    .filter((s) => s.rounds_completed > 0 && s.rounds_completed < s.round_count)
    .map((s) => `${s.season} ${afterRound(s)}`);
  const first = seasons
    .filter((s) => s.constructor_champion)
    .map((s) => s.season)
    .sort((a, b) => a - b)[0];
  return [
    "Source: f1db",
    ...running,
    ...(first === undefined ? [] : [`constructors' title awarded from ${first}`]),
  ].join(" · ");
}
