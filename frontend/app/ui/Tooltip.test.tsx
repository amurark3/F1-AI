import { act, fireEvent, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Tooltip } from "./Tooltip";

function renderTooltip() {
  render(
    <div>
      <Tooltip label="after round 19" className="ml-2" data-status="confirmed">
        Base: f1db v2026.19.0
      </Tooltip>
      <p>Elsewhere on the page</p>
    </div>,
  );
  const trigger = screen.getByRole("button", { name: "after round 19" });
  // jsdom lays nothing out; give the trigger a box near the top left.
  vi.spyOn(trigger, "getBoundingClientRect").mockReturnValue(new DOMRect(100, 100, 200, 20));
  return trigger;
}

function tip(): HTMLElement {
  return screen.getByRole("tooltip", { hidden: true });
}

describe("Tooltip", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("describes its trigger with a tooltip rendered outside any clipping parent", () => {
    const trigger = renderTooltip();

    expect(trigger).toHaveAccessibleDescription("Base: f1db v2026.19.0");
    expect(trigger).toHaveAttribute("type", "button");
    expect(trigger).toHaveAttribute("data-status", "confirmed");
    expect(trigger).toHaveClass("ml-2", "cursor-help");
    expect(tip().parentElement).toBe(document.body);
    expect(tip()).toHaveAttribute("data-state", "closed");
    expect(tip()).toHaveClass("invisible", "fixed");
  });

  it("opens on hover below the trigger and closes once the pointer has left", () => {
    const trigger = renderTooltip();

    fireEvent.pointerEnter(trigger);
    expect(tip()).toHaveAttribute("data-state", "open");
    expect(tip()).toHaveClass("visible");
    expect(tip()).toHaveStyle({ top: "128px", left: "100px" });

    fireEvent.pointerLeave(trigger);
    act(() => {
      vi.advanceTimersByTime(119);
    });
    expect(tip()).toHaveAttribute("data-state", "open");
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(tip()).toHaveAttribute("data-state", "closed");
  });

  it("stays open while the pointer crosses onto the tooltip", () => {
    const trigger = renderTooltip();

    fireEvent.pointerEnter(trigger);
    fireEvent.pointerLeave(trigger);
    fireEvent.pointerEnter(tip());
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(tip()).toHaveAttribute("data-state", "open");

    fireEvent.pointerLeave(tip());
    act(() => {
      vi.advanceTimersByTime(120);
    });
    expect(tip()).toHaveAttribute("data-state", "closed");
  });

  it("opens on keyboard focus and closes on blur", () => {
    const trigger = renderTooltip();

    fireEvent.focus(trigger);
    expect(tip()).toHaveAttribute("data-state", "open");
    fireEvent.blur(trigger);
    expect(tip()).toHaveAttribute("data-state", "closed");
  });

  it("closes on Escape from anywhere, and ignores other keys", () => {
    const trigger = renderTooltip();

    fireEvent.focus(trigger);
    fireEvent.keyDown(document.body, { key: "a" });
    expect(tip()).toHaveAttribute("data-state", "open");
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(tip()).toHaveAttribute("data-state", "closed");
  });

  it("pins open on a click (a tap, on touch screens) until a second click", () => {
    const trigger = renderTooltip();

    fireEvent.click(trigger);
    fireEvent.pointerLeave(trigger);
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(tip()).toHaveAttribute("data-state", "open");
    expect(tip()).toHaveStyle({ top: "128px" });

    fireEvent.click(trigger);
    expect(tip()).toHaveAttribute("data-state", "closed");
  });

  it("closes a pinned tooltip on a press outside it, but not on one inside", () => {
    const trigger = renderTooltip();
    fireEvent.click(trigger);

    fireEvent.pointerDown(tip());
    fireEvent.pointerDown(trigger);
    expect(tip()).toHaveAttribute("data-state", "open");
    fireEvent.pointerDown(screen.getByText("Elsewhere on the page"));
    expect(tip()).toHaveAttribute("data-state", "closed");

    fireEvent.click(trigger);
    fireEvent.pointerDown(document);
    expect(tip()).toHaveAttribute("data-state", "closed");
  });

  it.each([
    ["the page scrolls", () => fireEvent.scroll(window)],
    ["the window resizes", () => fireEvent(window, new Event("resize"))],
  ])("closes when %s, since a fixed tooltip would drift off its trigger", (_case, move) => {
    const trigger = renderTooltip();
    fireEvent.click(trigger);

    move();
    expect(tip()).toHaveAttribute("data-state", "closed");
  });

  it("drops a pending close when it unmounts", () => {
    const { unmount } = render(<Tooltip label="badge">detail</Tooltip>);
    fireEvent.pointerEnter(screen.getByRole("button"));
    fireEvent.pointerLeave(screen.getByRole("button"));
    expect(vi.getTimerCount()).toBe(1);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("renders only the trigger on the server, which has no document to portal into", () => {
    const html = renderToString(<Tooltip label="badge">detail</Tooltip>);

    expect(html).toContain(">badge</button>");
    expect(html).not.toContain("detail");
  });
});
