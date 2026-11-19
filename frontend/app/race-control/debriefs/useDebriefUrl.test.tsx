import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_DEBRIEF_URL, readRound, useDebriefUrl } from "./useDebriefUrl";

const nav = vi.hoisted(() => ({ search: "round=7", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/race-control/debriefs",
}));

describe("readRound", () => {
  it("reads a positive integer and nothing else", () => {
    expect(readRound(new URLSearchParams("round=12"))).toBe(12);
    for (const bad of ["round=0", "round=-3", "round=2.5", "round=abc", "round=", "round=07", ""]) {
      expect(readRound(new URLSearchParams(bad))).toBeNull();
    }
  });
});

describe("useDebriefUrl", () => {
  it("reads the round and writes a selection without scrolling", () => {
    const { result } = renderHook(() => useDebriefUrl());

    expect(result.current.round).toBe(7);
    result.current.select(9);
    expect(nav.replace).toHaveBeenCalledWith("/race-control/debriefs?round=9", { scroll: false });
  });

  it("has a default that selects nothing", () => {
    expect(DEFAULT_DEBRIEF_URL.round).toBeNull();
    expect(DEFAULT_DEBRIEF_URL.select(3)).toBeUndefined();
  });
});
