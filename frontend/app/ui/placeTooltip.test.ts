import { describe, expect, it } from "vitest";

import { TOOLTIP_MAX_WIDTH, placeTooltip } from "./placeTooltip";

const VIEWPORT = { width: 1280, height: 800 };

/** A 20 px tall, 200 px wide trigger whose top-left corner sits at (`left`, `top`). */
function trigger(left: number, top: number) {
  return { left, top, right: left + 200, bottom: top + 20 };
}

describe("placeTooltip", () => {
  it("opens below the trigger, aligned to its left edge", () => {
    expect(placeTooltip(trigger(100, 100), VIEWPORT)).toEqual({ top: 128, left: 100 });
  });

  it("opens upward near the bottom of the viewport", () => {
    expect(placeTooltip(trigger(100, 700), VIEWPORT)).toEqual({ bottom: 108, left: 100 });
  });

  it("stays below when there is even less room above", () => {
    const short = { width: 1280, height: 150 };
    expect(placeTooltip(trigger(100, 40), short)).toEqual({ top: 68, left: 100 });
  });

  it("aligns to the trigger's right edge when the widest tooltip would run off screen", () => {
    const left = VIEWPORT.width - TOOLTIP_MAX_WIDTH;
    expect(placeTooltip(trigger(left, 100), VIEWPORT)).toEqual({ top: 128, right: VIEWPORT.width - (left + 200) });
  });

  it("keeps a margin from the viewport edge when the trigger itself overflows", () => {
    expect(placeTooltip({ left: 1200, top: 100, right: 1300, bottom: 120 }, VIEWPORT)).toEqual({ top: 128, right: 8 });
  });
});
