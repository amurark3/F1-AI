import { act, render, screen, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Countdown } from "./Countdown";

const NOW = Date.UTC(2026, 10, 2, 4, 0, 0);
/** São Paulo practice 1, four days, 11 hours, 45 minutes and 30 seconds ahead. */
const FP1 = NOW + (((4 * 24 + 11) * 60 + 45) * 60 + 30) * 1000;

function cells(): string[] {
  return within(screen.getByRole("timer"))
    .getAllByText(/^(\d{2,}|--)$/)
    .map((cell) => cell.textContent ?? "");
}

describe("Countdown", () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: NOW });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("counts days, hours and minutes to the moment, as a named timer", () => {
    render(<Countdown target={new Date(FP1).toISOString()} label="Time to Practice 1" className="mt-3" />);

    const timer = screen.getByRole("timer", { name: "Time to Practice 1" });
    expect(timer).toHaveClass("mt-3");
    expect(cells()).toEqual(["04", "11", "45"]);
    expect(within(timer).getByText("days")).toHaveClass("font-mono", "text-rc-ink-3");
    expect(within(timer).getByText("hrs")).toBeInTheDocument();
    expect(within(timer).getByText("min")).toBeInTheDocument();
    expect(within(timer).queryByText("sec")).not.toBeInTheDocument();
    expect(within(timer).getByText("04")).toHaveClass("font-display", "text-[44px]");
  });

  it("ticks on the shared clock and adds seconds when asked", () => {
    render(<Countdown target={FP1} label="Time to Practice 1" seconds />);
    expect(cells()).toEqual(["04", "11", "45", "30"]);
    expect(screen.getByText("sec")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(31_000);
    });
    expect(cells()).toEqual(["04", "11", "44", "59"]);
  });

  it("reads all zeros once the moment has passed", () => {
    render(<Countdown target={new Date(NOW - 60_000)} label="Time to the race" />);
    expect(cells()).toEqual(["00", "00", "00"]);
  });

  it("sits inside a panel on smaller cells in the page colour", () => {
    render(<Countdown target={FP1} label="Lights out in" variant="panel" />);

    const digits = screen.getByText("04");
    expect(digits).toHaveClass("text-[38px]");
    expect(digits.parentElement).toHaveClass("bg-background", "min-w-[66px]");
  });

  it("shows dashes for a target that is not a date", () => {
    render(<Countdown target="TBC" label="Time to the race" />);
    expect(cells()).toEqual(["--", "--", "--"]);
  });

  it("renders dashes on the server, which has no honest now", () => {
    const html = renderToString(<Countdown target={FP1} label="Time to Practice 1" />);

    expect(html).toContain('role="timer"');
    expect(html.match(/>--</g)).toHaveLength(3);
    expect(html).not.toContain(">04<");
  });
});
