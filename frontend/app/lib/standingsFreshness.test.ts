import { describe, expect, it } from "vitest";

import { TEAMS_2026 } from "@/test/fixtures";

import { standingsLabel } from "./standingsFreshness";

describe("standingsLabel", () => {
  it("labels the captured R19 table as confirmed once f1db publishes the round", () => {
    expect(standingsLabel(TEAMS_2026)).toBe("after round 19 · confirmed");
  });

  it("labels a table that holds an unpublished round as provisional", () => {
    expect(standingsLabel({ ...TEAMS_2026, provisional: true })).toBe("after round 19 · provisional");
  });

  it("reads a payload without the provisional flag as confirmed", () => {
    expect(standingsLabel({ as_of_round: 3 })).toBe("after round 3 · confirmed");
  });

  it.each([
    ["no payload", null],
    ["an undefined payload", undefined],
    ["a payload without freshness fields", {}],
    ["a table before any round has points", { as_of_round: null, provisional: false }],
    ["round zero", { as_of_round: 0, provisional: true }],
  ])("gives no label for %s", (_case, freshness) => {
    expect(standingsLabel(freshness)).toBeNull();
  });
});
