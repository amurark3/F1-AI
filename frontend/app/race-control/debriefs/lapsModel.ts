/** Wording and runs for the lap strip, the race trace, the penalty timeline and the position-change board. */

import { driverLabel, type NameDirectory } from "@/app/ui/names/names";

import { redFlagLap } from "../grand-prix/strategyModel";

import type { DebriefDriver, DebriefLaps, DebriefOvertakes, DebriefPenalties, OvertakeDriver } from "./debriefTypes";
import type { Neutralisation } from "../grand-prix/strategyModel";

export interface LeaderRun {
  /** The leader's code; null for laps with no timing. */
  code: string | null;
  startLap: number;
  endLap: number;
}

/** Consecutive laps led by the same car (or by nobody), lap 1 first. */
export function leaderRuns(leaders: ReadonlyArray<string | null>): LeaderRun[] {
  return leaders.reduce<LeaderRun[]>((runs, code, index) => {
    const last = runs.at(-1);
    if (last?.code === code) return [...runs.slice(0, -1), { ...last, endLap: index + 1 }];
    return [...runs, { code, startLap: index + 1, endLap: index + 1 }];
  }, []);
}

function nameOf(
  drivers: readonly DebriefDriver[],
  code: string,
  variant: "full" | "last",
  dir?: NameDirectory,
): string {
  const driver = drivers.find((entry) => entry.driver_code === code);
  return driver ? driverLabel({ name: driver.driver_name, code }, variant, dir) : code;
}

/** "Leclerc led every lap" / "Verstappen led from lap 44 to the flag"; null when the last lap has no leader. */
export function stripTitle(laps: DebriefLaps, directory?: NameDirectory): string | null {
  const last = leaderRuns(laps.leaders).at(-1);
  if (!last?.code) return null;
  const who = nameOf(laps.drivers, last.code, "last", directory);
  return last.startLap === 1 ? `${who} led every lap` : `${who} led from lap ${last.startLap} to the flag`;
}

/** The strip's reading note: laps led per driver, most first, and the laps with no timing. */
export function stripSub(laps: DebriefLaps, directory?: NameDirectory): string {
  const led = new Map<string, number>();
  for (const code of laps.leaders) if (code) led.set(code, (led.get(code) ?? 0) + 1);
  const counts = [...led]
    .sort((a, b) => b[1] - a[1])
    .map(([code, n]) => `${nameOf(laps.drivers, code, "last", directory)} ${n}`);
  const untimed = laps.leaders.filter((code) => code === null).length;
  const base = `Each block is one lap, coloured by who led it at the line · ${counts.join(", ")} laps`;
  return untimed > 0 ? `${base} · ${untimed} ${untimed === 1 ? "lap" : "laps"} without timing` : base;
}

/** The strip as text for a screen reader: "Laps 1–27: Charles Leclerc". */
export function stripRuns(laps: DebriefLaps): Array<{ range: string; name: string }> {
  return leaderRuns(laps.leaders).flatMap((run) =>
    run.code
      ? [
          {
            range: run.startLap === run.endLap ? `Lap ${run.startLap}` : `Laps ${run.startLap}–${run.endLap}`,
            name: nameOf(laps.drivers, run.code, "full"),
          },
        ]
      : [],
  );
}

function countOf(neutralisations: readonly Neutralisation[], kind: Neutralisation["kind"]): number {
  return neutralisations.filter((period) => period.kind === kind).length;
}

/** "A VSC, 2 Safety Cars and a red flag after lap 45", or "No Safety Car, VSC or red flag". */
export function traceTitle(neutralisations: readonly Neutralisation[]): string {
  const vsc = countOf(neutralisations, "vsc");
  const sc = countOf(neutralisations, "sc");
  const red = countOf(neutralisations, "red");
  const parts = [
    vsc > 0 && (vsc === 1 ? "a VSC" : `${vsc} VSCs`),
    sc > 0 && (sc === 1 ? "a Safety Car" : `${sc} Safety Cars`),
    red > 0 && (red === 1 ? `a red flag after lap ${redFlagLap([...neutralisations])}` : `${red} red flags`),
  ].filter((part): part is string => part !== false);
  if (parts.length === 0) return "No Safety Car, VSC or red flag";
  const text = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function penaltyTitle(penalties: DebriefPenalties): string {
  const drivers = new Set([...penalties.in_race, ...penalties.post_race].map((row) => row.driver_code));
  if (drivers.size === 0) return "No penalties";
  return `${drivers.size} ${drivers.size === 1 ? "driver" : "drivers"} penalised`;
}

export function penaltySub(penalties: DebriefPenalties): string {
  const document = penalties.fia_document;
  if (!document) return "In-race from race control · post-race from f1db's time penalties";
  const number = document.number === null ? "" : ` (doc ${document.number})`;
  return `In-race from race control · post-race from the FIA final classification${number}`;
}

/** The board's finding: who made most position changes, or how many tied. */
export function overtakesTitle(overtakes: DebriefOvertakes, directory?: NameDirectory): string | null {
  const [top] = overtakes.drivers;
  if (!top) return null;
  const tied: OvertakeDriver[] = overtakes.drivers.filter((driver) => driver.made === top.made);
  const last = (driver: OvertakeDriver) =>
    driverLabel({ name: driver.driver_name, code: driver.driver_code }, "last", directory);
  if (tied.length === 1) return `${last(top)} made the most position changes`;
  if (tied.length === 2) return `${last(tied[0])} and ${last(tied[1])} made the most position changes`;
  return `${tied.length} drivers tied on ${top.made}`;
}
