import { describe, expect, it } from "vitest";

import { readParams } from "./useTelemetryParams";

describe("readParams segment", () => {
  const read = (query: string) => readParams(new URLSearchParams(query), 2026).segment;

  it("keeps a part from 1 to 3 and drops anything else", () => {
    expect(read("segment=3")).toBe(3);
    expect(read("segment=1")).toBe(1);
    expect(read("segment=4")).toBeNull();
    expect(read("segment=0")).toBeNull();
    expect(read("segment=q3")).toBeNull();
    expect(read("")).toBeNull();
  });
});
