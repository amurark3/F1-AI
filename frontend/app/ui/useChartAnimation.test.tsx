import { act, renderHook } from "@testing-library/react";
import { useReducedMotion } from "framer-motion";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CHART_EASING, CHART_ENTRANCE_MS, useChartAnimation } from "./useChartAnimation";

import type * as FramerMotion from "framer-motion";

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof FramerMotion>()),
  useReducedMotion: vi.fn(),
}));

function SeriesFlag() {
  return <>{String(useChartAnimation().series.isAnimationActive)}</>;
}

describe("useChartAnimation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(useReducedMotion).mockReturnValue(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("plays the entrance once, on the kit's curve, then never again", () => {
    const { result, rerender } = renderHook(() => useChartAnimation());
    expect(result.current).toEqual({
      active: true,
      series: {
        isAnimationActive: true,
        animationBegin: 0,
        animationDuration: CHART_ENTRANCE_MS,
        animationEasing: CHART_EASING,
      },
    });

    act(() => {
      vi.advanceTimersByTime(CHART_ENTRANCE_MS - 1);
    });
    expect(result.current.active).toBe(true);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.active).toBe(false);
    expect(result.current.series.isAnimationActive).toBe(false);

    rerender();
    expect(result.current.active).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("waits out a stagger delay before the entrance counts as over", () => {
    const { result } = renderHook(() => useChartAnimation({ delayMs: 300, durationMs: 600 }));
    expect(result.current.series).toMatchObject({ animationBegin: 300, animationDuration: 600 });

    act(() => {
      vi.advanceTimersByTime(899);
    });
    expect(result.current.active).toBe(true);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.active).toBe(false);
  });

  it.each([
    ["prefers reduced motion", true],
    ["has not reported a preference", null],
  ])("draws at once for a reader who %s", (_case, reduce) => {
    vi.mocked(useReducedMotion).mockReturnValue(reduce);
    const { result } = renderHook(() => useChartAnimation());

    expect(result.current.active).toBe(false);
    expect(result.current.series.isAnimationActive).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("drops its timer when the chart unmounts mid-entrance", () => {
    const { unmount } = renderHook(() => useChartAnimation());
    expect(vi.getTimerCount()).toBe(1);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("never animates the server render, which cannot know the preference", () => {
    expect(renderToString(<SeriesFlag />)).toBe("false");
  });
});
