import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { REWIND_R19 as r19 } from "@/test/fixtures/rewind";
import { race } from "@/test/fixtures/rewindHandBuilt";
import { renderWithProviders } from "@/test/render";

import { Scrubber } from "./Scrubber";

import type { RaceRewind } from "./rewindTypes";

function show(step: number, over: { data?: RaceRewind; playing?: boolean } = {}) {
  const onStep = vi.fn();
  const onToggle = vi.fn();
  const view = renderWithProviders(
    <Scrubber
      data={over.data ?? r19}
      step={step}
      playing={over.playing ?? false}
      onToggle={onToggle}
      onStep={onStep}
    />,
  );
  return { ...view, onStep, onToggle };
}

describe("the scrubber", () => {
  it("reads lap 44 under the Safety Car", () => {
    show(44);

    const range = screen.getByRole("slider", { name: "Lap" });
    expect(range).toHaveValue("44");
    expect(range).toHaveAttribute("max", "72");
    expect(range).toHaveAttribute("aria-valuetext", "After lap 44 of 71");
    expect(screen.getByText("After lap")).toBeInTheDocument();
    expect(screen.getByText("/ 71")).toBeInTheDocument();
    expect(screen.getByText("Safety Car")).toBeInTheDocument();
  });

  it("labels the end of the track and shades the neutralised laps", () => {
    const { container } = show(44);

    expect(screen.getByText("Grid")).toBeInTheDocument();
    expect(screen.getByText("L36")).toBeInTheDocument();
    expect(screen.getByText("Final")).toBeInTheDocument();
    expect(container.querySelectorAll("[aria-hidden] > span.absolute")).toHaveLength(3);
  });

  it("tags a VSC lap, a red-flag lap, and no tag on a green lap", () => {
    const { unmount } = show(8);
    expect(screen.getByText("VSC")).toBeInTheDocument();
    unmount();
    const red = show(45);
    expect(screen.getByText("Red flag")).toBeInTheDocument();
    red.unmount();
    show(10);
    expect(screen.queryByText(/Safety Car|VSC|Red flag/)).not.toBeInTheDocument();
  });

  it("says Grid and Final in place of the lap number", () => {
    const grid = show(0);
    expect(screen.getAllByText("Grid")).toHaveLength(2);
    expect(screen.queryByText("/ 71")).not.toBeInTheDocument();
    grid.unmount();
    show(72);
    expect(screen.getAllByText("Final")).toHaveLength(2);
  });

  it("ends on the last lap when no classification is published", () => {
    show(1, { data: race({ final: null }) });

    expect(screen.getByRole("slider", { name: "Lap" })).toHaveAttribute("max", "3");
    expect(screen.getByText("L3")).toBeInTheDocument();
    expect(screen.queryByText("Final")).not.toBeInTheDocument();
  });

  it("steps back and forward, and stops at the ends", async () => {
    const mid = show(44);
    await mid.user.click(screen.getByRole("button", { name: "Next lap" }));
    await mid.user.click(screen.getByRole("button", { name: "Previous lap" }));
    expect(mid.onStep.mock.calls).toEqual([[45], [43]]);
    mid.unmount();

    const first = show(0);
    expect(screen.getByRole("button", { name: "Previous lap" })).toBeDisabled();
    first.unmount();
    show(72);
    expect(screen.getByRole("button", { name: "Next lap" })).toBeDisabled();
  });

  it("follows the range, and plays or pauses on the button", async () => {
    const view = show(44);

    fireEvent.change(screen.getByRole("slider", { name: "Lap" }), { target: { value: "50" } });
    expect(view.onStep).toHaveBeenCalledWith(50);
    await view.user.click(screen.getByRole("button", { name: "▶ Play" }));
    expect(view.onToggle).toHaveBeenCalledOnce();
    view.unmount();

    show(44, { playing: true });
    expect(screen.getByRole("button", { name: "❚❚ Pause" })).toHaveAttribute("aria-pressed", "true");
  });
});
