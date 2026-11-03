import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RefreshButton } from "./RefreshButton";

/** Spinner floor and result hold, as in RefreshButton.tsx. */
const MIN_SPIN_MS = 550;
const RESULT_HOLD_MS = 1800;

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function button(): HTMLElement {
  return screen.getByRole("button");
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("RefreshButton", () => {
  it("spins in the fill red while refreshing, says Updated in neutral ink, then rests", async () => {
    const onRefresh = vi.fn<() => Promise<unknown>>().mockResolvedValue(undefined);
    render(<RefreshButton onRefresh={onRefresh} className="ml-auto" />);

    expect(button()).toHaveTextContent("Refresh");
    expect(button()).toHaveClass("ml-auto");
    expect(button().querySelector("svg")).not.toHaveClass("animate-spin");

    fireEvent.click(button());
    expect(onRefresh).toHaveBeenCalledOnce();
    expect(button()).toHaveTextContent("Refreshing");
    expect(button()).toBeDisabled();
    expect(button()).toHaveAttribute("aria-busy", "true");
    expect(button().querySelector("svg")).toHaveClass("text-f1-red", "animate-spin", "motion-reduce:animate-none");

    await advance(MIN_SPIN_MS);
    expect(button()).toHaveTextContent("Updated");
    expect(button()).toHaveClass("text-rc-ink", "border-rc-ink/35");
    expect(button().className).not.toMatch(/00FF78/i);
    expect(button()).toBeEnabled();

    await advance(RESULT_HOLD_MS);
    expect(button()).toHaveTextContent("Refresh");
  });

  it("reports a failed refresh in red and logs it", async () => {
    const error = new Error("offline");
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<RefreshButton onRefresh={() => Promise.reject(error)} />);

    fireEvent.click(button());
    await advance(MIN_SPIN_MS);

    expect(button()).toHaveTextContent("Refresh failed");
    expect(button()).toHaveClass("text-[#FF6B67]");
    expect(log).toHaveBeenCalledWith("Refresh failed:", error);
  });

  it("does not wait past the floor when the refresh itself was slow", async () => {
    render(
      <RefreshButton
        onRefresh={() =>
          new Promise((resolve) => {
            setTimeout(resolve, MIN_SPIN_MS + 200);
          })
        }
      />,
    );

    fireEvent.click(button());
    await advance(MIN_SPIN_MS + 200);
    // The floor is spent, so only a zero-length wait is left: well short of another 550 ms.
    await advance(1);
    await advance(1);

    expect(button()).toHaveTextContent("Updated");
  });

  it("starts over when clicked again while it still shows the result", async () => {
    const onRefresh = vi.fn<() => Promise<unknown>>().mockResolvedValue(undefined);
    render(<RefreshButton onRefresh={onRefresh} />);

    fireEvent.click(button());
    await advance(MIN_SPIN_MS);
    fireEvent.click(button());
    expect(button()).toHaveTextContent("Refreshing");

    // The first result's hold was cleared, so it cannot reset the second run early.
    await advance(MIN_SPIN_MS);
    expect(button()).toHaveTextContent("Updated");
    await advance(RESULT_HOLD_MS - 1);
    expect(button()).toHaveTextContent("Updated");
    expect(onRefresh).toHaveBeenCalledTimes(2);
  });

  it("settles nothing after it unmounts mid-refresh", async () => {
    const { unmount } = render(<RefreshButton onRefresh={() => Promise.resolve()} />);

    fireEvent.click(button());
    unmount();
    await advance(MIN_SPIN_MS + RESULT_HOLD_MS);

    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears its pending reset when it unmounts showing a result", async () => {
    const { unmount } = render(<RefreshButton onRefresh={() => Promise.resolve()} />);

    fireEvent.click(button());
    await advance(MIN_SPIN_MS);
    expect(vi.getTimerCount()).toBe(1);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
