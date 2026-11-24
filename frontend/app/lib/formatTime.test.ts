import { afterEach, describe, expect, it, vi } from "vitest";

import { formatLocal, formatUtc, resolvedTimeZone } from "./formatTime";

describe("formatTime", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("formats in UTC and en-US whatever the host says", () => {
    expect(formatUtc("2026-09-11T13:35:00Z", "stamp", "—")).toBe("Sep 11, 01:35 PM");
  });

  it("formats with the host's own locale and zone for the viewer", () => {
    const host = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });

    expect(formatLocal("2026-09-11T13:35:00Z", "clock", "—")).toBe(host.format(new Date("2026-09-11T13:35:00Z")));
  });

  it.each([undefined, null, "", "not a date"])("returns the fallback for %j", (value) => {
    expect(formatUtc(value, "day", "n/a")).toBe("n/a");
  });

  it("names the host zone, or UTC when it names none", () => {
    expect(resolvedTimeZone()).not.toBe("");
    vi.spyOn(Intl, "DateTimeFormat").mockReturnValue({
      resolvedOptions: () => ({ timeZone: "" }),
    } as Intl.DateTimeFormat);

    expect(resolvedTimeZone()).toBe("UTC");
  });
});
