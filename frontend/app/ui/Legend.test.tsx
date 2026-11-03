import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Legend, type LegendItem } from "./Legend";
import { f1, rc } from "./tokens";

/** The Mexico City stint chart's key, from the mockups. */
const STINTS: LegendItem[] = [
  { label: "Soft", color: "#e8002d" },
  { label: "Pit stop", color: rc.ink, mark: "rule" },
  { label: "Still available", color: rc.line, mark: "outline" },
  { label: "a retirement counts as finishing behind" },
];

function markOf(label: string): HTMLElement | null {
  return screen.getByText(label).querySelector("[data-mark]");
}

describe("Legend", () => {
  it("lists each mark and label in the mono caption tone", () => {
    render(<Legend items={STINTS} className="mt-3.5" />);

    const list = screen.getByRole("list", { name: "Legend" });
    expect(list).toHaveClass("mt-3.5", "font-mono", "text-rc-ink-3", "flex-wrap");
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(STINTS.map((item) => item.label));
  });

  it("draws a filled square by default, a thin rule for an event and an empty square on request", () => {
    render(<Legend items={STINTS} />);

    const soft = markOf("Soft");
    expect(soft).toHaveAttribute("data-mark", "swatch");
    expect(soft).toHaveAttribute("aria-hidden", "true");
    expect(soft).toHaveStyle({ backgroundColor: "#e8002d" });
    expect(soft).toHaveClass("size-3");

    const stop = markOf("Pit stop");
    expect(stop).toHaveClass("w-0.5");
    expect(stop).toHaveStyle({ backgroundColor: rc.ink });

    const available = markOf("Still available");
    expect(available).toHaveClass("border");
    expect(available).toHaveStyle({ borderColor: rc.line });
    expect(available?.style.backgroundColor).toBe("");
  });

  it("leaves a note without a mark", () => {
    render(<Legend items={STINTS} />);
    expect(markOf("a retirement counts as finishing behind")).toBeNull();
  });

  it("takes its own accessible name", () => {
    render(<Legend items={[{ label: "Red flag", color: f1.red, mark: "rule" }]} label="Race trace key" />);
    expect(screen.getByRole("list", { name: "Race trace key" })).toBeInTheDocument();
  });
});
