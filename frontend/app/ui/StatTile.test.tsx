import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatTile, StatTiles } from "./StatTile";

/** Mercedes after round 19, from the team mockup. */
function MercedesRow() {
  return (
    <StatTiles className="mt-5">
      <StatTile lead label="Wins" value={12} unit="of 19" sub="Antonelli 9 · Russell 3" />
      <StatTile label="Podiums" value={24} sub="of 38 starts" />
      <StatTile label="Poles" value={12} />
    </StatTiles>
  );
}

describe("StatTile", () => {
  it("shows a label, the figure in display type, its unit and a caption", () => {
    render(<StatTile label="Lap" value="4.309" unit="km" sub="Interlagos" className="p-4" />);

    const figure = screen.getByText("4.309");
    expect(figure).toHaveClass("font-display", "tabular-nums", "text-[40px]");
    expect(screen.getByText("km")).toHaveClass("text-rc-ink-3", "text-[0.45em]");
    expect(screen.getByText("km").parentElement).toBe(figure);
    expect(screen.getByText("Lap")).toHaveClass("font-mono", "uppercase");
    expect(screen.getByText("Interlagos")).toHaveClass("text-rc-ink-3");

    const tile = figure.parentElement;
    expect(tile).toHaveClass("p-4");
    expect(tile).not.toHaveAttribute("data-lead");
  });

  it("shows the bare figure when it has no unit or caption", () => {
    render(<StatTile label="Laps" value={71} />);

    const figure = screen.getByText("71");
    expect(figure.children).toHaveLength(0);
    expect(figure.parentElement?.children).toHaveLength(2);
  });

  it("gives the lead tile the larger figure and marks it for the wider column", () => {
    render(<StatTile lead label="Wins" value={12} />);

    const figure = screen.getByText("12");
    expect(figure).toHaveClass("text-[56px]");
    expect(figure.parentElement).toHaveAttribute("data-lead");
  });
});

describe("StatTiles", () => {
  it("rules a row of tiles, the lead half again as wide, stacking below lg", () => {
    const { container } = render(<MercedesRow />);

    const row = container.firstElementChild;
    expect(row?.children).toHaveLength(3);
    expect(row).toHaveClass(
      "mt-5",
      "border-y",
      "border-rc-line",
      "divide-y",
      "lg:grid",
      "lg:grid-flow-col",
      "lg:auto-cols-fr",
      "lg:divide-x",
      "lg:[&>*]:col-span-2",
      "lg:[&>[data-lead]]:col-span-3",
    );
    expect(row?.firstElementChild).toHaveAttribute("data-lead");
    expect(screen.getByText("of 19")).toBeInTheDocument();
  });

  it("works without a class of its own", () => {
    const { container } = render(
      <StatTiles>
        <StatTile label="Corners" value={15} />
      </StatTiles>,
    );
    expect(container.firstElementChild?.className).not.toContain("undefined");
    expect(screen.getByText("15")).toBeInTheDocument();
  });
});
