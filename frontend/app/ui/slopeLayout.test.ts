import { describe, expect, it } from "vitest";

import {
  deltaText,
  SLOPE,
  slopeDelta,
  slopeLayout,
  slopeValueText,
  spokenChange,
  spreadLabels,
  trendOf,
} from "./slopeLayout";

describe("slopeLayout on the position scale", () => {
  it("gives every slot one row, P1 at the top, as the debrief grid → finish chart does", () => {
    // Mexico City 2026: VER P5 → P1, RUS P2 → P6, LAW pit lane (slot 22) → P7.
    const layout = slopeLayout(
      [
        { start: 5, end: 1 },
        { start: 2, end: 6 },
        { start: 22, end: 7 },
      ],
      "position",
    );

    expect(layout.width).toBe(SLOPE.width);
    // 21 row gaps from P1 to slot 22, plus the margins: debrief.html's 668-unit-tall figure.
    expect(layout.height).toBe(SLOPE.top + 21 * SLOPE.rowGap + SLOPE.bottom);
    expect(layout.rows[0]).toEqual({ y1: 34 + 4 * 29.5, y2: 34, labelY1: 34 + 4 * 29.5, labelY2: 34 });
    expect(layout.rows[2].y1).toBe(34 + 21 * 29.5);
    expect(layout.rows[2].y2).toBe(34 + 6 * 29.5);
  });

  it("starts the scale at the best slot drawn, so a midfield battle is not pushed down the chart", () => {
    const layout = slopeLayout(
      [
        { start: 11, end: 12 },
        { start: 12, end: 11 },
      ],
      "position",
    );
    expect(layout.rows[0].y1).toBe(SLOPE.top);
    expect(layout.rows[0].y2).toBe(SLOPE.top + SLOPE.rowGap);
    expect(layout.height).toBe(SLOPE.top + SLOPE.rowGap + SLOPE.bottom);
  });
});

describe("slopeLayout on the value scale", () => {
  it("puts the higher value at the top over a plot of at least the minimum rows", () => {
    // Points before and after R19: ANT 355 → 380, VER 243 → 261.
    const layout = slopeLayout(
      [
        { start: 355, end: 380 },
        { start: 243, end: 261 },
      ],
      "value",
    );
    const plot = SLOPE.minValueRows * SLOPE.rowGap;

    expect(layout.height).toBe(SLOPE.top + plot + SLOPE.bottom);
    expect(layout.rows[0].y2).toBe(SLOPE.top);
    expect(layout.rows[1].y1).toBe(SLOPE.top + plot);
    expect(layout.rows[0].y1).toBeCloseTo(SLOPE.top + ((380 - 355) / (380 - 243)) * plot);
  });

  it("grows the plot by one row per entity past the minimum", () => {
    const pairs = Array.from({ length: 10 }, (_, index) => ({ start: index, end: index * 2 }));
    expect(slopeLayout(pairs, "value").height).toBe(SLOPE.top + 9 * SLOPE.rowGap + SLOPE.bottom);
  });

  it("sets equal values across the middle of the plot", () => {
    const layout = slopeLayout([{ start: 7, end: 7 }], "value");
    const middle = SLOPE.top + (SLOPE.minValueRows * SLOPE.rowGap) / 2;
    expect(layout.rows[0]).toMatchObject({ y1: middle, y2: middle });
  });

  it("nudges labels apart where the values sit too close to read", () => {
    // VER 261 and HAM 259 land a unit apart; their labels must not overprint.
    const layout = slopeLayout(
      [
        { start: 380, end: 380 },
        { start: 261, end: 261 },
        { start: 259, end: 259 },
      ],
      "value",
    );
    const [, ver, ham] = layout.rows;
    expect(ham.y1 - ver.y1).toBeLessThan(SLOPE.labelMinGap);
    expect(ham.labelY1 - ver.labelY1).toBeGreaterThanOrEqual(SLOPE.labelMinGap);
    expect(ham.labelY2).toBeLessThanOrEqual(SLOPE.top + SLOPE.minValueRows * SLOPE.rowGap);
  });
});

describe("slopeLayout with nothing to draw", () => {
  it("is only the margins", () => {
    expect(slopeLayout([], "position")).toEqual({
      width: SLOPE.width,
      height: SLOPE.top + SLOPE.bottom,
      rows: [],
    });
  });
});

describe("spreadLabels", () => {
  it("leaves labels that already clear each other where they are", () => {
    expect(spreadLabels([10, 40, 70], 14, [0, 100])).toEqual([10, 40, 70]);
  });

  it("pushes a crowded label down, keeping the order of the points", () => {
    expect(spreadLabels([40, 30, 32], 14, [0, 100])).toEqual([58, 30, 44]);
  });

  it("pulls labels back up when the push would run past the bottom", () => {
    expect(spreadLabels([90, 95, 100], 14, [0, 100])).toEqual([72, 86, 100]);
  });

  it("handles one label and none", () => {
    expect(spreadLabels([50], 14, [0, 100])).toEqual([50]);
    expect(spreadLabels([], 14, [0, 100])).toEqual([]);
  });
});

describe("slopeDelta", () => {
  it("counts places gained as positive: up the order is down the number", () => {
    expect(slopeDelta(5, 1, "position")).toBe(4);
    expect(slopeDelta(2, 6, "position")).toBe(-4);
  });

  it("counts a rise in value as positive", () => {
    expect(slopeDelta(243, 261, "value")).toBe(18);
    expect(slopeDelta(10, 7.5, "value")).toBe(-2.5);
  });
});

describe("trendOf", () => {
  it("names the direction of a change", () => {
    expect([3, -1, 0, -0].map(trendOf)).toEqual(["gain", "loss", "even", "even"]);
  });
});

describe("text", () => {
  it("writes positions as P-numbers and values as plain numbers", () => {
    expect(slopeValueText(7, "position")).toBe("P7");
    expect(slopeValueText(1234.56, "value")).toBe("1,234.6");
  });

  it("signs a change with a real minus, never colour alone", () => {
    expect(deltaText(4)).toBe("+4");
    expect(deltaText(-4)).toBe("−4");
    expect(deltaText(0)).toBe("0");
    expect(deltaText(-2.5)).toBe("−2.5");
  });

  it("says the change in words for a screen reader", () => {
    expect(spokenChange(4, "position")).toBe("gained 4 places");
    expect(spokenChange(-1, "position")).toBe("lost 1 place");
    expect(spokenChange(0, "position")).toBe("no change");
    expect(spokenChange(18, "value")).toBe("up 18");
    expect(spokenChange(-2.5, "value")).toBe("down 2.5");
    expect(spokenChange(0, "value")).toBe("no change");
  });
});
