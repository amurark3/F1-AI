import { describe, expect, it, vi } from "vitest";

import { measurementId } from "./measurementId";

describe("measurementId", () => {
  it("accepts a GA4 measurement ID", () => {
    expect(measurementId("G-AB12CD34EF")).toBe("G-AB12CD34EF");
  });

  it.each([undefined, "", "UA-1234567-1", "G-ab12cd", "G-AB12');alert(1)//"])(
    "rejects %j, since it is pasted into an inline script",
    (raw) => {
      expect(measurementId(raw)).toBeNull();
    },
  );

  it("reads the ID from the build-time env", async () => {
    vi.stubEnv("NEXT_PUBLIC_GA_ID", "G-TEST1234");
    vi.resetModules();
    const fresh = await import("./measurementId");

    expect(fresh.GA_ID).toBe("G-TEST1234");
    vi.unstubAllEnvs();
  });
});
