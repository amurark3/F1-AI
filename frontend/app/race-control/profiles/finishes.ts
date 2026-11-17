/**
 * How a car's classification reads on the profile pages.
 *
 * Every non-finish reads its status code with the reason, never a place, even
 * when f1db classified the car (docs/DATA_SOURCES.md, "Accuracy rules").
 * Components read finishes only through these helpers.
 */
import type { Finish, FinishStatus } from "./profilesModel";

type OutStatus = Exclude<FinishStatus, "finished">;

const CODES: Record<OutStatus, string> = {
  dnf: "DNF",
  dns: "DNS",
  dsq: "DSQ",
  nc: "NC",
  dnq: "DNQ",
  ex: "EX",
};

const WORDS: Record<OutStatus, string> = {
  dnf: "Retired",
  dns: "Did not start",
  dsq: "Disqualified",
  nc: "Not classified",
  dnq: "Did not qualify",
  ex: "Excluded",
};

export function isFinished(finish: Finish): boolean {
  return finish.status === "finished";
}

/** "DNF", "DNS" …; a finisher has no code, so its place stands in. */
export function statusCode(finish: Finish): string {
  return finish.status === "finished" ? `P${finish.position}` : CODES[finish.status];
}

/** "Retired", "Did not start" …; "Finished" for a finisher. */
export function statusWord(finish: Finish): string {
  return finish.status === "finished" ? "Finished" : WORDS[finish.status];
}

/** "P4", or the status code. */
export function finishText(finish: Finish): string {
  return statusCode(finish);
}

function signed(places: number): string {
  return places < 0 ? `−${Math.abs(places)}` : `+${places}`;
}

function finisherSentence(finish: Finish): string {
  const place = `P${finish.position}`;
  if (finish.pit_lane) {
    const gain =
      finish.positions_gained === null
        ? ""
        : ` (${signed(finish.positions_gained)}, counted from the back of the grid)`;
    return `pit lane → ${place}${gain}`;
  }
  return finish.grid === null ? place : `P${finish.grid} → ${place}`;
}

function outSentence(finish: Finish): string {
  const reason = finish.reason_retired ? ` (${finish.reason_retired})` : "";
  const classified = finish.position === null ? "" : `, classified P${finish.position}`;
  return `${statusWord(finish).toLowerCase()}${reason}${classified} · ${finish.points} pts`;
}

/**
 * One finish in words, for tooltips and screen readers:
 * "R9 British GP: retired (Spun off), classified P20 · 0 pts".
 */
export function finishSentence(roundLabel: string, finish: Finish): string {
  return `${roundLabel}: ${isFinished(finish) ? finisherSentence(finish) : outSentence(finish)}`;
}
