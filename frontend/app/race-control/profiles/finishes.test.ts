import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { finishSentence, finishText, isFinished, statusCode, statusWord } from "./finishes";

import type { Finish, FinishStatus } from "./profilesModel";

function finish(over: Partial<Finish> = {}): Finish {
  return {
    number: 3,
    position: 4,
    position_text: "4",
    grid: 7,
    points: 12,
    positions_gained: 3,
    reason_retired: null,
    fastest_lap: false,
    pole: false,
    status: "finished",
    pit_lane: false,
    ...over,
  };
}

const STATES: Array<[FinishStatus, string, string]> = [
  ["dnf", "DNF", "Retired"],
  ["dns", "DNS", "Did not start"],
  ["dsq", "DSQ", "Disqualified"],
  ["nc", "NC", "Not classified"],
  ["dnq", "DNQ", "Did not qualify"],
  ["ex", "EX", "Excluded"],
];

describe("finish states", () => {
  it("tells a finisher from every other state", () => {
    expect(isFinished(finish())).toBe(true);
    expect(isFinished(finish({ status: "dnf" }))).toBe(false);
  });

  it.each(STATES)("reads %s as its code and its word", (status, code, word) => {
    const out = finish({ status, position: null, position_text: code });
    expect(statusCode(out)).toBe(code);
    expect(statusWord(out)).toBe(word);
    expect(finishText(out)).toBe(code);
  });

  it("prints a finisher's place", () => {
    expect(finishText(finish())).toBe("P4");
    expect(statusWord(finish())).toBe("Finished");
  });
});

describe("finishSentence", () => {
  it("reads a grid-to-flag move for a finisher", () => {
    expect(finishSentence("R1 Australian GP", finish({ grid: 7, position: 4 }))).toBe("R1 Australian GP: P7 → P4");
  });

  it("reads a finish with no grid slot recorded as the place alone", () => {
    expect(finishSentence("R1 Australian GP", finish({ grid: null }))).toBe("R1 Australian GP: P4");
  });

  it("names a classified retirement, its reason and the place it was classified in", () => {
    const out = finish({
      status: "dnf",
      position: 20,
      position_text: "20",
      reason_retired: "Spun off",
      points: 0,
      positions_gained: null,
    });
    expect(finishSentence("R9 British GP", out)).toBe("R9 British GP: retired (Spun off), classified P20 · 0 pts");
  });

  it("names an unclassified non-start without a place or a reason", () => {
    const out = finish({ status: "dns", position: null, position_text: "DNS", points: 0, positions_gained: null });
    expect(finishSentence("R2 Chinese GP", out)).toBe("R2 Chinese GP: did not start · 0 pts");
  });

  it("labels a pit-lane start and where its gain is counted from", () => {
    const out = finish({ grid: null, pit_lane: true, position: 7, positions_gained: 15 });
    expect(finishSentence("R19 Mexican GP", out)).toBe(
      "R19 Mexican GP: pit lane → P7 (+15, counted from the back of the grid)",
    );
  });

  it("writes a pit-lane loss with a true minus, and a pit-lane start with no gain plainly", () => {
    expect(finishSentence("R5 X", finish({ grid: null, pit_lane: true, position: 18, positions_gained: -2 }))).toBe(
      "R5 X: pit lane → P18 (−2, counted from the back of the grid)",
    );
    expect(finishSentence("R5 X", finish({ grid: null, pit_lane: true, position: 18, positions_gained: null }))).toBe(
      "R5 X: pit lane → P18",
    );
  });

  it("reads Verstappen's R9 in the captured fixture as a retirement, never a 20th place", () => {
    const row = PROFILE_PAGES_2026.red_bull.rounds[8]?.results.find((item) => item.driver_id === "max-verstappen");
    expect(row?.race && finishSentence("R9 British GP", row.race)).toContain("retired (Spun off)");
  });
});
