import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PLAY_STEP_MS, PLAY_STEP_REDUCED_MS, usePlayback } from "./usePlayback";

const motion = vi.hoisted(() => ({ reduced: false }));

vi.mock("framer-motion", () => ({ useReducedMotion: () => motion.reduced }));

function setup(start: number, max: number) {
  const onStep = vi.fn();
  const view = renderHook(({ step }) => usePlayback(step, max, onStep), { initialProps: { step: start } });
  return { ...view, onStep };
}

describe("usePlayback", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    motion.reduced = false;
  });
  afterEach(() => vi.useRealTimers());

  it("steps once every 600 ms and stops at the last step", () => {
    const { result, rerender, onStep } = setup(2, 4);

    act(() => result.current.toggle());
    expect(result.current.playing).toBe(true);
    act(() => void vi.advanceTimersByTime(PLAY_STEP_MS));
    expect(onStep).toHaveBeenLastCalledWith(3);
    rerender({ step: 3 });
    act(() => void vi.advanceTimersByTime(PLAY_STEP_MS));
    expect(onStep).toHaveBeenLastCalledWith(4);
    expect(result.current.playing).toBe(false);
    act(() => void vi.advanceTimersByTime(PLAY_STEP_MS * 3));
    expect(onStep).toHaveBeenCalledTimes(2);
  });

  it("steps every 1500 ms for a reader who prefers reduced motion", () => {
    motion.reduced = true;
    const { result, onStep } = setup(0, 4);

    act(() => result.current.toggle());
    act(() => void vi.advanceTimersByTime(PLAY_STEP_REDUCED_MS - 1));
    expect(onStep).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(1));
    expect(onStep).toHaveBeenCalledWith(1);
  });

  it("restarts from the grid when played at the last step", () => {
    const { result, onStep } = setup(4, 4);

    act(() => result.current.toggle());

    expect(onStep).toHaveBeenCalledWith(0);
    expect(result.current.playing).toBe(true);
  });

  it("pauses on a toggle or a manual pause, and clears its timer on unmount", () => {
    const { result, unmount, onStep } = setup(0, 4);

    act(() => result.current.toggle());
    act(() => result.current.toggle());
    expect(result.current.playing).toBe(false);
    act(() => result.current.toggle());
    act(() => result.current.pause());
    expect(result.current.playing).toBe(false);
    act(() => result.current.toggle());
    unmount();
    act(() => void vi.advanceTimersByTime(PLAY_STEP_MS * 2));
    expect(onStep).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
