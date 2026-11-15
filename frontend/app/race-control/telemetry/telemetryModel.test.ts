import { describe, expect, it } from "vitest";

import { formatGap, formatLapTime } from "./telemetryModel";

describe("formatLapTime", () => {
  it("writes minutes and a padded fraction, or just seconds under a minute", () => {
    expect(formatLapTime(94.035)).toBe("1:34.035");
    expect(formatLapTime(61.5)).toBe("1:01.500");
    expect(formatLapTime(59.5)).toBe("59.500");
    expect(formatLapTime(5.25)).toBe("05.250");
  });

  it("shows a dash when there is no time", () => {
    expect(formatLapTime(null)).toBe("-");
    expect(formatLapTime(undefined)).toBe("-");
  });
});

describe("formatGap", () => {
  it("signs a gap and keeps the digits asked for", () => {
    expect(formatGap(0.325)).toBe("+0.325");
    expect(formatGap(-0.12)).toBe("-0.120");
    expect(formatGap(0)).toBe("0.000");
    expect(formatGap(1.234, 1)).toBe("+1.2");
  });

  it("shows a dash when there is no gap", () => {
    expect(formatGap(null)).toBe("-");
    expect(formatGap(undefined)).toBe("-");
  });
});
