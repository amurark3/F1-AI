import { describe, expect, it } from "vitest";

import { WEEKEND_FEED_2026_R19 } from "@/test/fixtures";

import {
  carCounts,
  changesResult,
  docLabel,
  feedRows,
  feedTitle,
  isCorrected,
  outcomesText,
  outcomeText,
  printedSubject,
  type FeedEvent,
  type StewardsDecision,
} from "./fiaFeedModel";

const EVENTS = WEEKEND_FEED_2026_R19.events;
const doc = (number: number): FeedEvent => EVENTS.find((event) => event.number === number)!;

describe("feedRows", () => {
  it("lists the 44 decisions, summonses, deleted-lap sheets and grids, newest first", () => {
    const rows = feedRows(EVENTS);
    expect(rows).toHaveLength(44);
    expect(rows.map((row) => row.number)).toEqual([...rows.map((row) => row.number)].sort((a, b) => b! - a!));
    for (const out of [58, 64, 66, 86]) expect(rows.some((row) => row.number === out)).toBe(false);
  });

  it("keeps a grid sheet it could not read", () => {
    const unreadable = { ...doc(67), data: null, unread: "no grid table" } as FeedEvent;
    expect(feedRows([unreadable])).toHaveLength(1);
  });
});

describe("outcome text", () => {
  it.each([
    [{ kind: "time_penalty", value: 10 }, "10 s time penalty"],
    [{ kind: "grid_drop", value: 5 }, "5-place grid drop"],
    [{ kind: "back_of_grid", value: null }, "Back of the grid"],
    [{ kind: "pit_lane_start", value: null }, "Pit-lane start"],
    [{ kind: "disqualified", value: null }, "Disqualified"],
    [{ kind: "stop_and_go", value: null }, "Stop-and-go"],
    [{ kind: "drive_through", value: null }, "Drive-through"],
    [{ kind: "reprimand", value: null }, "Reprimand"],
    [{ kind: "warning", value: null }, "Warning"],
    [{ kind: "fine", value: 5000 }, "€5,000 fine"],
    [{ kind: "penalty_points", value: 1 }, "1 penalty point"],
    [{ kind: "penalty_points", value: 2 }, "2 penalty points"],
    [{ kind: "no_further_action", value: null }, "No further action"],
    [{ kind: "time_penalty", value: null }, "Time penalty"],
    [{ kind: "grid_drop", value: null }, "Grid drop"],
    [{ kind: "fine", value: null }, "Fine"],
    [{ kind: "penalty_points", value: null }, "Penalty points"],
    [{ kind: "lost_the_plot", value: null }, "Lost the plot"],
  ])("%j reads %s", (outcome, text) => {
    expect(outcomeText(outcome)).toBe(text);
  });

  it("joins outcomes, and falls back to the decision line", () => {
    const decision = (doc(84) as Extract<FeedEvent, { kind: "penalty" }>).data!;
    expect(outcomesText(decision)).toBe("Stop-and-go + 2 penalty points");
    const bare: StewardsDecision = { ...decision, outcomes: [], decision: "As printed." };
    expect(outcomesText(bare)).toBe("As printed.");
    expect(outcomesText({ ...bare, decision: null })).toBe("");
  });
});

describe("changesResult", () => {
  it("is true for a standing time penalty or stop-and-go, false otherwise", () => {
    expect(changesResult(doc(79))).toBe(true);
    expect(changesResult(doc(84))).toBe(true);
    expect(changesResult(doc(83))).toBe(false);
    expect(changesResult(doc(76))).toBe(false);
    expect(changesResult(doc(82))).toBe(false);
    expect(changesResult(doc(80))).toBe(false);
    expect(changesResult({ ...doc(79), withdrawn: "withdrawn by Doc 90" })).toBe(false);
    expect(changesResult({ ...doc(79), data: null })).toBe(false);
  });
});

describe("feedTitle", () => {
  it("counts the fixture", () => {
    expect(feedTitle(feedRows(EVENTS))).toBe("24 decisions, 98 laps deleted");
  });

  it("handles singular, one-sided and empty rows, and skips withdrawn ones", () => {
    const sheet = doc(80) as Extract<FeedEvent, { kind: "deleted_laps" }>;
    const oneLap = { ...sheet, data: { ...sheet.data!, laps: sheet.data!.laps.slice(0, 1) } };
    expect(feedTitle([doc(79), oneLap])).toBe("1 decision, 1 lap deleted");
    expect(feedTitle([doc(79), doc(84)])).toBe("2 decisions");
    expect(feedTitle([sheet])).toBe("13 laps deleted");
    expect(feedTitle([{ ...doc(79), withdrawn: "x" }, { ...sheet, withdrawn: "x" }, doc(82)])).toBe("No decisions yet");
    expect(feedTitle([{ ...sheet, data: null }])).toBe("No decisions yet");
    expect(feedTitle([])).toBe("No decisions yet");
  });
});

describe("carCounts", () => {
  it("orders by count, then car", () => {
    const sheet = doc(80) as Extract<FeedEvent, { kind: "deleted_laps" }>;
    expect(carCounts(sheet.data!.laps).map(({ car, count }) => [car, count])).toEqual([
      [1, 2],
      [5, 2],
      [10, 2],
      [50, 2],
      [81, 2],
      [18, 1],
      [23, 1],
      [27, 1],
    ]);
  });
});

describe("labels", () => {
  it("names a document, strips its prefix and spots a correction", () => {
    expect(docLabel(doc(79))).toBe("Doc 79");
    expect(docLabel({ number: null })).toBe("FIA document");
    expect(printedSubject("Doc 79 - Infringement - Car 81")).toBe("Infringement - Car 81");
    expect(isCorrected("Doc 5 - Corrected Decision")).toBe(true);
    expect(isCorrected("Doc 5 - Decision")).toBe(false);
  });
});
