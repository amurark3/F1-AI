import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ColumnBars, type ColumnBarItem } from "./ColumnBars";

function item(over: Partial<ColumnBarItem> & { id: string }): ColumnBarItem {
  return { axis: `R${over.id}`, value: 10, description: `Round ${over.id}: ${over.value ?? 10}`, ...over };
}

function bar(index: number): HTMLElement {
  const found = screen.getAllByRole("listitem")[index]?.querySelector<HTMLElement>("[data-bar]");
  if (!found) throw new Error(`no bar at ${index}`);
  return found;
}

describe("ColumnBars", () => {
  it("names the list and gives each column its axis label and a sentence for screen readers", () => {
    render(
      <ColumnBars label="Points by weekend" items={[item({ id: "1", value: 55, description: "R1: 55 points" })]} />,
    );

    const list = screen.getByRole("list", { name: "Points by weekend" });
    const column = within(list).getByRole("listitem");
    expect(column).toHaveAttribute("title", "R1: 55 points");
    expect(within(column).getByText("R1: 55 points", { selector: ".sr-only" })).toBeInTheDocument();
    expect(within(column).getByText("R1", { selector: "[data-axis]" })).toBeInTheDocument();
  });

  it("scales bars to the largest value, or to max when given", () => {
    const items = [item({ id: "1", value: 50 }), item({ id: "2", value: 25 })];
    const { rerender } = render(<ColumnBars label="x" items={items} />);
    expect(bar(0).style.height).toBe("100%");
    expect(bar(1).style.height).toBe("50%");

    rerender(<ColumnBars label="x" items={items} max={100} />);
    expect(bar(0).style.height).toBe("50%");
  });

  it("caps a value over max at the full plot", () => {
    render(<ColumnBars label="x" items={[item({ id: "1", value: 30 })]} max={25} />);
    expect(bar(0).style.height).toBe("100%");
  });

  it("splits at a zero line when any value is negative, growing losses downward", () => {
    const { container } = render(
      <ColumnBars label="x" items={[item({ id: "1", value: 4 }), item({ id: "2", value: -2 })]} />,
    );
    expect(container.querySelector("[data-zero-line]")).not.toBeNull();
    expect(bar(0).style.height).toBe("50%");
    expect(bar(0).className).toContain("origin-bottom");
    expect(bar(1).style.height).toBe("25%");
    expect(bar(1).className).toContain("origin-top");
  });

  it("sets a marker and a zero tick on the zero line of a split plot", () => {
    render(
      <ColumnBars
        label="x"
        items={[
          item({ id: "1", value: -2 }),
          item({ id: "2", value: 0 }),
          item({ id: "3", value: null, marker: "DNF", markerTone: "alert" }),
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[1]?.querySelector("[data-tick]")?.className).toContain("top-1/2");
    expect(within(items[2]).getByText("DNF").className).toContain("top-1/2");
  });

  it("draws no zero line when nothing is negative", () => {
    const { container } = render(<ColumnBars label="x" items={[item({ id: "1" })]} />);
    expect(container.querySelector("[data-zero-line]")).toBeNull();
  });

  it("draws a zero as a tick, not a bar", () => {
    render(<ColumnBars label="x" items={[item({ id: "1", value: 0 }), item({ id: "2", value: 5 })]} />);
    const column = screen.getAllByRole("listitem")[0];
    expect(column.querySelector("[data-bar]")).toBeNull();
    expect(column.querySelector("[data-tick]")).not.toBeNull();
  });

  it("replaces the bar with a marker when there is no value, in its tone", () => {
    render(
      <ColumnBars
        label="x"
        items={[
          item({ id: "1", value: null, marker: "DNF", markerTone: "alert" }),
          item({ id: "2", value: null, marker: "—", markerTone: "muted" }),
          item({ id: "3", value: null, marker: "DNS" }),
          item({ id: "4", value: null }),
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[0]?.querySelector("[data-bar]")).toBeNull();
    expect(within(items[0]).getByText("DNF").className).toContain("text-rc-red-text");
    expect(within(items[1]).getByText("—").className).toContain("text-rc-ink-3");
    expect(within(items[2]).getByText("DNS").className).toContain("text-rc-ink-3");
    expect(items[3]?.querySelector("[data-marker]")).toBeNull();
  });

  it("shows the value text from sm up, in the bar's colour and with entrance motion behind motion-safe", () => {
    render(<ColumnBars label="x" items={[item({ id: "1", value: 55, valueText: "55", color: "rgb(1, 2, 3)" })]} />);
    expect(bar(0).style.backgroundColor).toBe("rgb(1, 2, 3)");
    expect(bar(0).className).toContain("motion-safe:animate-rise-y");
    expect(screen.getByText("55", { selector: "[data-value]" }).className).toMatch(/hidden.*sm:block/);
  });

  it("puts a negative bar's figure under it", () => {
    render(
      <ColumnBars
        label="x"
        items={[item({ id: "1", value: 3, valueText: "+3" }), item({ id: "2", value: -2, valueText: "−2" })]}
      />,
    );
    expect(screen.getByText("−2", { selector: "[data-value]" }).className).toContain("top-full");
    expect(screen.getByText("+3", { selector: "[data-value]" }).className).toContain("bottom-full");
  });

  it("scrolls sideways inside its own box with 20 px a column, and takes a height", () => {
    render(<ColumnBars label="x" height={200} className="extra" items={[item({ id: "1" }), item({ id: "2" })]} />);
    const list = screen.getByRole("list");
    expect(list.style.minWidth).toBe("40px");
    expect(list.style.height).toBe("200px");
    expect(list.parentElement?.className).toContain("overflow-x-auto");
    expect(list.parentElement?.className).toContain("extra");
  });

  it("copes with no items and with all-zero values", () => {
    const { rerender } = render(<ColumnBars label="x" items={[]} />);
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    rerender(<ColumnBars label="x" items={[item({ id: "1", value: 0 })]} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });
});
