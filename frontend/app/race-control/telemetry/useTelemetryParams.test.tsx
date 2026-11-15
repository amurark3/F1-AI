import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { readParams, useTelemetryParams } from "./useTelemetryParams";

const nav = vi.hoisted(() => ({ search: "", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/race-control/telemetry",
}));

const read = (query: string) => readParams(new URLSearchParams(query), 2026);

describe("readParams", () => {
  it("opens the speed map on this season with nothing chosen", () => {
    expect(read("")).toEqual({
      tab: "map",
      year: 2026,
      round: null,
      session: null,
      a: null,
      b: null,
      lap: null,
      segment: null,
    });
  });

  it("keeps every valid param, normalising case", () => {
    expect(read("tab=head-to-head&year=2024&round=7&session=q&a=ant&b=RUS&lap=14&segment=2")).toEqual({
      tab: "head-to-head",
      year: 2024,
      round: 7,
      session: "Q",
      a: "ANT",
      b: "RUS",
      lap: 14,
      segment: 2,
    });
  });

  it("drops anything malformed", () => {
    expect(read("tab=nope&year=2022&round=0&session=zzz&a=ab&b=1234&lap=x&segment=9")).toEqual(read(""));
    expect(read("year=2027").year).toBe(2026);
    expect(read("year=abc").year).toBe(2026);
  });

  it("keeps a segment from 1 to 3 and drops anything else", () => {
    expect(read("segment=3").segment).toBe(3);
    expect(read("segment=1").segment).toBe(1);
    expect(read("segment=4").segment).toBeNull();
    expect(read("segment=0").segment).toBeNull();
    expect(read("segment=q3").segment).toBeNull();
  });
});

describe("useTelemetryParams", () => {
  beforeEach(() => {
    nav.replace.mockClear();
    nav.search = "tab=tyres&year=2025&round=3&session=R&a=ANT&b=RUS&lap=5&segment=2";
  });

  it("reads the URL", () => {
    const { result } = renderHook(() => useTelemetryParams(2026));
    expect(result.current.params).toMatchObject({ tab: "tyres", year: 2025, round: 3, session: "R" });
  });

  it("writes a change back to the URL, keeping the rest and dropping nulls", () => {
    const { result } = renderHook(() => useTelemetryParams(2026));
    act(() => {
      result.current.update({ round: 4, lap: null, segment: null });
    });
    expect(nav.replace).toHaveBeenCalledWith(
      "/race-control/telemetry?tab=tyres&year=2025&round=4&session=R&a=ANT&b=RUS",
      {
        scroll: false,
      },
    );
  });

  it("writes only the tab and year when nothing else is chosen", () => {
    nav.search = "";
    const { result } = renderHook(() => useTelemetryParams(2026));
    act(() => {
      result.current.update({ tab: "head-to-head" });
    });
    expect(nav.replace).toHaveBeenCalledWith("/race-control/telemetry?tab=head-to-head&year=2026", { scroll: false });
  });
});
