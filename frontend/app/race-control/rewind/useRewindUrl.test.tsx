import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_REWIND_URL, readStep, useRewindUrl } from "./useRewindUrl";

const nav = vi.hoisted(() => ({ search: "round=19&lap=44", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/race-control/rewind",
}));

describe("readStep", () => {
  it("reads a whole number from 0, or the final step, and nothing else", () => {
    expect(readStep(new URLSearchParams("lap=44"))).toBe(44);
    expect(readStep(new URLSearchParams("lap=0"))).toBe(0);
    expect(readStep(new URLSearchParams("lap=final"))).toBe("final");
    for (const bad of ["lap=-1", "lap=2.5", "lap=x", "lap=", "lap=044", "lap=Final", ""]) {
      expect(readStep(new URLSearchParams(bad))).toBeNull();
    }
  });
});

describe("useRewindUrl", () => {
  it("reads the round and the step", () => {
    const { result } = renderHook(() => useRewindUrl());

    expect(result.current.round).toBe(19);
    expect(result.current.step).toBe(44);
  });

  it("selects a race through the router, dropping the step", () => {
    const { result } = renderHook(() => useRewindUrl());

    result.current.select(7);

    expect(nav.replace).toHaveBeenCalledWith("/race-control/rewind?round=7", { scroll: false });
  });

  it("writes a step with the history API, never the router", () => {
    nav.replace.mockClear();
    const write = vi.spyOn(window.history, "replaceState");
    const { result } = renderHook(() => useRewindUrl());

    result.current.setStep(19, 45);
    result.current.setStep(19, "final");

    expect(write).toHaveBeenCalledWith(null, "", "/race-control/rewind?round=19&lap=45");
    expect(write).toHaveBeenCalledWith(null, "", "/race-control/rewind?round=19&lap=final");
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("has a default that names nothing and writes nothing", () => {
    expect(DEFAULT_REWIND_URL.round).toBeNull();
    expect(DEFAULT_REWIND_URL.step).toBeNull();
    expect(DEFAULT_REWIND_URL.select(3)).toBeUndefined();
    expect(DEFAULT_REWIND_URL.setStep(3, 4)).toBeUndefined();
  });
});
