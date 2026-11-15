import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { listMove, useActiveOption } from "./useActiveOption";

import type { KeyboardEvent } from "react";

/** A key press, with the spy its `preventDefault` reports to. */
function press(key: string): { event: KeyboardEvent; prevented: ReturnType<typeof vi.fn> } {
  const prevented = vi.fn();
  return { event: { key, preventDefault: prevented } as unknown as KeyboardEvent, prevented };
}

describe("listMove", () => {
  it("steps with the arrows, stopping at either end", () => {
    expect(listMove("ArrowLeft", 3, 23)).toBe(2);
    expect(listMove("ArrowUp", 0, 23)).toBe(0);
    expect(listMove("ArrowRight", 3, 23)).toBe(4);
    expect(listMove("ArrowDown", 22, 23)).toBe(22);
  });

  it("jumps to the first and last with Home and End, and ignores every other key", () => {
    expect(listMove("Home", 9, 23)).toBe(0);
    expect(listMove("End", 9, 23)).toBe(22);
    expect(listMove("a", 9, 23)).toBeNull();
  });
});

describe("useActiveOption", () => {
  it("starts on the selected option, moves with the keys and commits the active one", () => {
    const onCommit = vi.fn();
    const { result } = renderHook(() => useActiveOption(23, 19, onCommit));

    expect(result.current.active).toBeNull();
    act(() => result.current.onFocus());
    expect(result.current.active).toBe(19);

    const left = press("ArrowLeft");
    act(() => result.current.onKeyDown(left.event));
    expect(left.prevented).toHaveBeenCalled();
    expect(result.current.active).toBe(18);

    act(() => result.current.onKeyDown(press("Enter").event));
    expect(onCommit).toHaveBeenLastCalledWith(18);
    act(() => result.current.onKeyDown(press(" ").event));
    expect(onCommit).toHaveBeenCalledTimes(2);

    const other = press("Tab");
    act(() => result.current.onKeyDown(other.event));
    expect(other.prevented).not.toHaveBeenCalled();

    act(() => result.current.reset());
    expect(result.current.active).toBeNull();
  });

  it("moves from the selected option before any is active, and from the first when none is selected", () => {
    const onCommit = vi.fn();
    const { result } = renderHook(() => useActiveOption(23, -1, onCommit));

    act(() => result.current.onKeyDown(press("Enter").event));
    expect(onCommit).toHaveBeenCalledWith(0);
    act(() => result.current.onKeyDown(press("ArrowRight").event));
    expect(result.current.active).toBe(1);
  });
});
