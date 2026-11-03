import { act, renderHook } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useClock } from "./useClock";

const START = Date.UTC(2026, 10, 2, 12, 0, 0);

function ClockText() {
  return <>{String(useClock())}</>;
}

describe("useClock", () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: START });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reads the wall clock on mount and ticks once a second", () => {
    const { result } = renderHook(() => useClock());
    expect(result.current).toBe(START);

    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(result.current).toBe(START);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe(START + 1000);
  });

  it("shares one interval between every countdown and stops it with the last", () => {
    const first = renderHook(() => useClock());
    const second = renderHook(() => useClock());
    expect(vi.getTimerCount()).toBe(1);

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(first.result.current).toBe(START + 2000);
    expect(second.result.current).toBe(START + 2000);

    first.unmount();
    expect(vi.getTimerCount()).toBe(1);
    second.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("restarts from the current time for a countdown mounted later", () => {
    renderHook(() => useClock()).unmount();
    vi.setSystemTime(START + 60_000);

    const { result } = renderHook(() => useClock());
    expect(result.current).toBe(START + 60_000);
  });

  it("is null on the server, which has no honest now", () => {
    expect(renderToString(<ClockText />)).toBe("null");
    expect(vi.getTimerCount()).toBe(0);
  });
});
