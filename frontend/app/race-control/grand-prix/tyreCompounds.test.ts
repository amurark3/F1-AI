import { describe, expect, it } from "vitest";

import { f1 } from "@/app/ui/tokens";

import {
  UNKNOWN_COMPOUND_COLOR,
  compoundColor,
  compoundInitial,
  compoundLabel,
  compoundTextColor,
  compoundsUsed,
} from "./tyreCompounds";

describe("tyreCompounds", () => {
  it("colours each compound from its token, old names included, and an unknown one grey", () => {
    expect(compoundColor("soft")).toBe(f1.tyreSoft);
    expect(compoundColor("MEDIUM")).toBe(f1.tyreMedium);
    expect(compoundColor("HARD")).toBe(f1.tyreHard);
    expect(compoundColor("INTERMEDIATE")).toBe(f1.tyreInter);
    expect(compoundColor("WET")).toBe(f1.tyreWet);
    expect(compoundColor("SUPERSOFT")).toBe(f1.tyreSoft);
    expect(compoundColor("ULTRASOFT")).toBe(f1.tyreUltrasoft);
    expect(compoundColor("HYPERSOFT")).toBe(f1.tyreHypersoft);
    expect(compoundColor("SUPERHARD")).toBe(f1.tyreHard);
    expect(compoundColor(null)).toBe(UNKNOWN_COMPOUND_COLOR);
    expect(compoundColor("PLASTIC")).toBe(f1.tyreUnknown);
  });

  it("names a compound by its initial and label, and says so when it is not recorded", () => {
    expect(compoundInitial("MEDIUM")).toBe("M");
    expect(compoundInitial("ULTRASOFT")).toBe("U");
    expect(compoundInitial(null)).toBe("?");
    expect(compoundLabel("SOFT")).toBe("Soft");
    expect(compoundLabel(null)).toBe("Not recorded");
  });

  it("prints dark text on the light compounds and light text on the rest", () => {
    expect(compoundTextColor("HARD")).toBe("var(--surface)");
    expect(compoundTextColor("MEDIUM")).toBe("var(--surface)");
    expect(compoundTextColor("SOFT")).toBe("var(--rc-ink)");
    expect(compoundTextColor(null)).toBe("var(--rc-ink)");
  });

  it("lists the compounds in a race softest first, then any others alphabetically", () => {
    expect(compoundsUsed(["HARD", null, "SOFT", "hard", "ULTRASOFT", "HYPERSOFT"])).toEqual([
      "SOFT",
      "HARD",
      "HYPERSOFT",
      "ULTRASOFT",
    ]);
  });
});
