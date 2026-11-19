import type { DriverChampion, RaceWinner, SeasonDetail } from "@/app/lib/server/champions";
import { formatPoints as pts } from "@/app/race-control/profiles/profilesModel";
import type { LegendItem } from "@/app/ui/Legend";
import { driverLabel, teamLabel } from "@/app/ui/names/names";
import { rc } from "@/app/ui/tokens";

import { afterRound, stillToRun, titleState } from "../championsModel";

/** The first constructors' title. One season payload can't tell "before it existed" from "no standings yet". */
export const FIRST_CONSTRUCTORS_TITLE = 1958;

/** Past this share of the season the decider's flag opens leftwards, so it stays inside the card. */
const FLAG_FLIP = 0.6;

export interface SeasonTile {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  lead?: boolean;
}

export interface RoundTick {
  round: number;
  run: boolean;
  team: string | null;
  championWon: boolean;
  decider: boolean;
  /** Phones label only these rounds. */
  keep: boolean;
  tip: string;
  flag: { text: string; side: "start" | "end" } | null;
}

export interface WinnerRow {
  round: number;
  winners: RaceWinner[];
  team: string | null;
  teamId: string | null;
  raceName: string;
  date: string;
  decider: boolean;
  shared: boolean;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function lastName(driver: DriverChampion): string {
  return driverLabel({ name: driver.name, lastName: driver.last_name }, "last");
}

const roundsLeft = (d: SeasonDetail): number => d.round_count - d.rounds_completed;

/** "8 Mar". */
export function dayMonth(iso: string | null): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(iso));
}

export function seasonEyebrow(d: SeasonDetail): string {
  if (!d.driver_champion) return `${d.season} season`;
  const state = titleState(d);
  if (state === "open") return `${d.season} championship leader`;
  return state === "clinched" ? `${d.season} World Champion · clinched` : `${d.season} World Champion`;
}

export function seasonMeta(d: SeasonDetail): string | undefined {
  const driver = d.driver_champion;
  if (!driver) return undefined;
  const state = titleState(d);
  let tail: string | null = null;
  if (state === "open") {
    tail = `Leads ${afterRound(d)}; the title is still open.`;
  } else if (d.decided_at) {
    const { round, place } = d.decided_at;
    tail = `Title decided in round ${round}${place ? `, ${place}` : ""}.${
      state === "clinched" ? ` ${stillToRun(roundsLeft(d))}.` : ""
    }`;
  }
  const parts = [driver.team, tail].filter((part): part is string => part !== null);
  return parts.length > 0 ? parts.join(" · ") : undefined;
}

function driverTiles(d: SeasonDetail): SeasonTile[] {
  const driver = d.driver_champion;
  if (!driver) return [];
  const tiles: SeasonTile[] = [
    {
      label: "Points",
      value: pts(driver.points),
      unit: "pts",
      sub: titleState(d) === "final" ? "final total" : afterRound(d),
      lead: true,
    },
    { label: "Wins", value: `${driver.wins}`, unit: `of ${d.rounds_completed}` },
  ];
  const ru = d.runner_up;
  if (ru) {
    const name = driverLabel({ name: ru.name, lastName: ru.last_name }, "full");
    tiles.push({
      label: titleState(d) === "open" ? "Lead" : "Margin",
      value: pts(driver.points - ru.points),
      unit: "pts",
      sub: `over ${name} · ${pts(ru.points)} pts`,
    });
  }
  return tiles;
}

function constructorTile(d: SeasonDetail): SeasonTile | null {
  const c = d.constructor_champion;
  if (!c) {
    return d.season < FIRST_CONSTRUCTORS_TITLE
      ? { label: "Constructors' champion", value: "—", sub: `title awarded from ${FIRST_CONSTRUCTORS_TITLE}` }
      : null;
  }
  return {
    label: c.title_decided ? "Constructors' champion" : "Constructors' leader",
    value: teamLabel({ name: c.name, year: d.season }, "name"),
    sub: `${pts(c.points)} pts${d.rounds_completed < d.round_count ? ` ${afterRound(d)}` : ""}`,
  };
}

export function seasonTiles(d: SeasonDetail): SeasonTile[] {
  const constructor = constructorTile(d);
  return [...driverTiles(d), ...(constructor ? [constructor] : [])];
}

export function ribbonTitle(d: SeasonDetail, driver: DriverChampion): string {
  const head = `${plural(driver.wins, "win")} for ${lastName(driver)}`;
  if (titleState(d) === "open") return `${head}, title still open after round ${d.rounds_completed}`;
  if (!d.decided_at) return head;
  const spare = d.round_count - d.decided_at.round;
  return `${head}, ${spare === 0 ? "decided at the last round" : `decided with ${plural(spare, "round")} to spare`}`;
}

function byRound(winners: RaceWinner[]): Map<number, RaceWinner[]> {
  const groups = new Map<number, RaceWinner[]>();
  for (const w of winners) groups.set(w.round, [...(groups.get(w.round) ?? []), w]);
  return groups;
}

function tickTip(round: number, winners: RaceWinner[] | undefined): string {
  if (!winners) return `R${round} · still to run`;
  const parts = [`R${round}`, winners.map((w) => w.winner).join(" / "), winners[0].team];
  return [...parts, ...(winners.length > 1 ? ["shared drive"] : [])].filter(Boolean).join(" · ");
}

export function roundTicks(d: SeasonDetail): RoundTick[] {
  const groups = byRound(d.race_winners ?? []);
  const champion = d.driver_champion?.name;
  const place = d.decided_at?.place;
  return Array.from({ length: d.round_count }, (_, i) => {
    const round = i + 1;
    const winners = groups.get(round);
    const decider = d.decided_at?.round === round;
    return {
      round,
      run: winners !== undefined,
      team: winners?.[0].team ?? null,
      championWon: winners?.some((w) => w.winner === champion) ?? false,
      decider,
      keep: round === 1 || decider || round === d.round_count,
      tip: tickTip(round, winners),
      flag: decider
        ? {
            text: place ? `Title decided · ${place}` : "Title decided",
            side: round / d.round_count > FLAG_FLIP ? "end" : "start",
          }
        : null,
    };
  });
}

export function ribbonLegend(d: SeasonDetail, driver: DriverChampion): LegendItem[] {
  return [
    { label: `${lastName(driver)}'s win`, color: rc.ink },
    ...(d.decided_at ? [{ label: "Title decided", color: rc.gold, mark: "rule" as const }] : []),
    ...(d.rounds_completed < d.round_count ? [{ label: "Still to run", color: rc.dim }] : []),
    { label: "Bar = the winning car's team" },
  ];
}

export function winnerRows(d: SeasonDetail): WinnerRow[] {
  return [...byRound(d.race_winners ?? [])]
    .sort(([a], [b]) => a - b)
    .map(([round, winners]) => ({
      round,
      winners,
      team: winners[0].team,
      teamId: winners[0].team_id ?? null,
      raceName: winners[0].race_name,
      date: dayMonth(winners[0].date),
      decider: d.decided_at?.round === round,
      shared: winners.length > 1,
    }));
}

/** The closing row for rounds not yet run, or null once every round has. */
export function toRunRow(d: SeasonDetail): { span: string; text: string } | null {
  if (d.rounds_completed >= d.round_count) return null;
  const first = d.rounds_completed + 1;
  return {
    span: first === d.round_count ? `R${first}` : `R${first}–R${d.round_count}`,
    text: stillToRun(roundsLeft(d)),
  };
}

export const roundsAside = (d: SeasonDetail): string => `${d.rounds_completed} of ${d.round_count} rounds`;

export function seasonSource(d: SeasonDetail): string {
  const running = d.rounds_completed > 0 && d.rounds_completed < d.round_count;
  return running ? `Source: f1db · ${d.season} ${afterRound(d)}` : "Source: f1db";
}
