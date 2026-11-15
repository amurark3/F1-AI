import { describe, expect, it } from "vitest";

import { PREDICTION_REVIEW_R19, RACE_RESULTS_2026 } from "@/test/fixtures";

import {
  buildReviewRows,
  chartTitle,
  placedRows,
  retiredRows,
  retirementTitle,
  trackPercent,
  trackSize,
  winnerSub,
  withinThree,
} from "./reviewModel";

import type { PredictionDriverResult } from "./predictionModel";

const REVIEW = PREDICTION_REVIEW_R19.prediction_review!;
const RESULTS = RACE_RESULTS_2026.mexicoCity;
const ROWS = buildReviewRows(REVIEW, RESULTS);
const SURNAME = (code: string) => ({ BOR: "Bortoleto", ALB: "Albon", VER: "Verstappen" })[code] ?? code;

function result(overrides: Partial<PredictionDriverResult>): PredictionDriverResult {
  return {
    driver_code: "AAA",
    predicted_position: 5,
    actual_position: 5,
    position_delta: 0,
    exact: true,
    status: "Finished",
    dnf: false,
    crash: false,
    ...overrides,
  };
}

describe("buildReviewRows (Mexico City, the real stored review)", () => {
  it("holds one row per called car in called order: 17 placed, 5 retired", () => {
    expect(ROWS).toHaveLength(22);
    expect(ROWS.map((row) => row.called)).toEqual(Array.from({ length: 22 }, (_, index) => index + 1));
    expect(placedRows(ROWS)).toHaveLength(17);
  });

  it("gives a classified car its delta: positive finished ahead of the call", () => {
    const hamilton = ROWS.find((row) => row.code === "HAM");
    expect(hamilton).toEqual({ kind: "placed", code: "HAM", called: 4, finished: 2, delta: 2 });
    expect(ROWS.find((row) => row.code === "LEC")).toMatchObject({ called: 2, finished: 4, delta: -2 });
  });

  it("reads a retirement as DNF with the classification's reason and laps, and no place or delta", () => {
    const lindblad = ROWS.find((row) => row.code === "LIN");
    expect(lindblad).toEqual({
      kind: "out",
      code: "LIN",
      called: 8,
      status: "DNF",
      detail: "Collision · 58 laps",
      risk: 13,
      flagged: false,
    });
    expect(ROWS.find((row) => row.code === "BEA")).toMatchObject({
      detail: "Collision damage · 47 laps",
      flagged: true,
    });
    expect(lindblad).not.toHaveProperty("delta");
  });

  it("falls back to the status when Results has not loaded", () => {
    expect(buildReviewRows(REVIEW, undefined).find((row) => row.code === "LIN")).toMatchObject({ detail: "DNF" });
  });

  it("skips a car that raced without being called, and reads a missing status as DNF with no risk figure", () => {
    const rows = buildReviewRows(
      {
        evaluated: true,
        driver_results: [
          result({ driver_code: "SUB", predicted_position: null, actual_position: 3, position_delta: null }),
          result({
            driver_code: "OUT",
            predicted_position: 2,
            actual_position: null,
            position_delta: null,
            status: null,
          }),
        ],
      },
      undefined,
    );
    expect(rows).toEqual([
      { kind: "out", code: "OUT", called: 2, status: "DNF", detail: "DNF", risk: null, flagged: false },
    ]);
  });

  it("reads a review with no rows as empty", () => {
    expect(buildReviewRows({ evaluated: true }, undefined)).toEqual([]);
  });
});

describe("what the strip and panels say", () => {
  it("counts the retirements by risk, highest first, flagged at 16% or more", () => {
    const retired = retiredRows(ROWS);
    expect(retired.map((row) => [row.code, row.risk, row.flagged])).toEqual([
      ["BOT", 36, true],
      ["STR", 25, true],
      ["ALO", 23, true],
      ["BEA", 20, true],
      ["LIN", 13, false],
    ]);
  });

  it("sorts a retirement with no risk figure last", () => {
    const rows = buildReviewRows(
      {
        evaluated: true,
        driver_results: [
          result({
            driver_code: "NOR",
            predicted_position: 1,
            actual_position: null,
            position_delta: null,
            status: "DNF",
          }),
          result({
            driver_code: "YES",
            predicted_position: 2,
            actual_position: null,
            position_delta: null,
            status: "DNF",
            predicted_dnf_risk_pct: 5,
          }),
          result({
            driver_code: "NUL",
            predicted_position: 3,
            actual_position: null,
            position_delta: null,
            status: "DNF",
          }),
        ],
      },
      undefined,
    );
    expect(retiredRows(rows).map((row) => row.code)).toEqual(["YES", "NOR", "NUL"]);
  });

  it("leaves a non-starter out of the retirements", () => {
    const rows = buildReviewRows(
      {
        evaluated: true,
        driver_results: [
          result({ actual_position: null, position_delta: null, status: "DNS", predicted_dnf_risk_pct: 40 }),
        ],
      },
      undefined,
    );
    expect(retiredRows(rows)).toEqual([]);
    expect(rows[0]).toMatchObject({ status: "DNS", flagged: true });
  });

  it("counts cars within three places over the classified cars only", () => {
    expect(withinThree(ROWS)).toBe(10);
  });

  it("titles the chart with the car or cars that beat the call by most", () => {
    expect(chartTitle(ROWS, SURNAME)).toBe("Bortoleto and Albon beat the call by 7 places");
  });

  it("names a lone best car in the singular and a single place in the singular", () => {
    const rows = buildReviewRows(
      {
        evaluated: true,
        driver_results: [result({ driver_code: "VER", predicted_position: 3, actual_position: 2, position_delta: -1 })],
      },
      undefined,
    );
    expect(chartTitle(rows, SURNAME)).toBe("Verstappen beats the call by 1 place");
  });

  it("says so when no classified car beat its call", () => {
    expect(chartTitle([], SURNAME)).toBe("No classified car beat its call");
  });

  it("titles the retirement panel from the review's counts", () => {
    expect(retirementTitle(REVIEW)).toBe("The risk model flagged 4 of the 5 retirements");
    expect(retirementTitle({ evaluated: true, dnf_correct: 1, dnf_actual: 1 })).toBe(
      "The risk model flagged 1 of the 1 retirement",
    );
    expect(retirementTitle({ evaluated: true })).toBe("No car retired");
  });

  it("says who was called and who won", () => {
    const name = (code: string) => `<${code}>`;
    expect(winnerSub(REVIEW, name)).toBe("Called <VER> P1 · they won");
    expect(winnerSub({ ...REVIEW, winner_correct: false, actual_winner: "LEC" }, name)).toBe(
      "Called <VER> · <LEC> won",
    );
    expect(winnerSub({ evaluated: true }, name)).toBe("No winner recorded");
  });
});

describe("the track", () => {
  it("places P1 at the left edge and the last place at the right", () => {
    expect(trackPercent(1, 22)).toBe(0);
    expect(trackPercent(22, 22)).toBe(100);
    expect(trackPercent(1, 1)).toBe(0);
  });

  it("is as long as the lowest place any call or result sits at, and never shorter than two", () => {
    expect(trackSize(ROWS)).toBe(22);
    expect(trackSize([])).toBe(2);
  });
});
