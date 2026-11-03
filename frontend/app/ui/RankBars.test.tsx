import { render, screen, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { RankBars, type RankBarItem } from "./RankBars";
import { BAR_STAGGER_MS } from "./rankBarScale";
import { rc } from "./tokens";

/** The drivers' order after R19, from standings.html. */
const DRIVERS: RankBarItem[] = [
  {
    id: "antonelli",
    rank: 1,
    label: "Kimi Antonelli",
    detail: "ANT",
    value: 380,
    aside: "—",
    color: "#27f4d2",
  },
  { id: "verstappen", rank: 2, label: "Max Verstappen", detail: "VER", value: 261, aside: "−119", color: "#3671c6" },
  { id: "hamilton", rank: 3, label: "Lewis Hamilton", detail: "HAM", value: 259, aside: "−121", color: "#e8002d" },
];

/** Retirement risk from gp-predictions.html: no places, a percentage scale. */
const RISK: RankBarItem[] = [
  { id: "bottas", label: "Valtteri Bottas", value: 36, valueText: "36%", color: "#e0d4b8" },
  { id: "alonso", label: "Fernando Alonso", value: 26, valueText: "26%", color: "#229971" },
];

function rows(name: string): HTMLElement[] {
  return within(screen.getByRole("list", { name })).getAllByRole("listitem");
}

function fillOf(row: HTMLElement): HTMLElement {
  const fill = row.querySelector<HTMLElement>("[data-fill]");
  if (fill === null) throw new Error("row has no bar");
  return fill;
}

describe("RankBars", () => {
  it("lists the rows in the order given, each with its place, name, code, figure and gap", () => {
    render(<RankBars items={DRIVERS} label="Drivers' championship points" />);

    expect(rows("Drivers' championship points").map((row) => row.textContent)).toEqual([
      "1Kimi Antonelli ANT380—",
      "2Max Verstappen VER261−119",
      "3Lewis Hamilton HAM259−121",
    ]);
    expect(screen.getByText("ANT")).toHaveClass("font-mono", "text-rc-ink-3");
    expect(screen.getByText("−119")).toHaveClass("text-rc-ink-3");
  });

  it("draws each bar in its colour, from zero against the leader, hidden from assistive tech", () => {
    render(<RankBars items={DRIVERS} label="Points" />);

    const [leader, second] = rows("Points");
    expect(fillOf(leader)).toHaveStyle({ width: "100%", backgroundColor: "#27f4d2" });
    expect(fillOf(second)).toHaveStyle({ width: "68.68%", backgroundColor: "#3671c6" });
    expect(fillOf(second).parentElement).toHaveAttribute("aria-hidden", "true");
    expect(fillOf(second).parentElement).toHaveClass("h-2.5", "bg-rc-ink/3");
  });

  it("staggers the bars' entrance row by row, behind motion-safe only", () => {
    render(<RankBars items={DRIVERS} label="Points" />);

    const fills = rows("Points").map(fillOf);
    expect(fills.map((fill) => fill.style.animationDelay)).toEqual([
      "0ms",
      `${BAR_STAGGER_MS}ms`,
      `${2 * BAR_STAGGER_MS}ms`,
    ]);
    expect(fills[0]).toHaveClass("origin-left", "motion-safe:animate-fill-x");

    const html = renderToString(<RankBars items={DRIVERS} label="Points" />);
    expect(html).not.toMatch(/(^|[\s"])animate-/);
  });

  it("adds the place and gap columns only when the rows carry them", () => {
    render(<RankBars items={DRIVERS} label="With places" />);
    render(<RankBars items={RISK} label="Without places" />);

    const withPlaces = screen.getByRole("list", { name: "With places" });
    expect(withPlaces.style.gridTemplateColumns).toBe(
      "max-content fit-content(260px) minmax(48px, 1fr) max-content max-content",
    );
    const withoutPlaces = screen.getByRole("list", { name: "Without places" });
    expect(withoutPlaces.style.gridTemplateColumns).toBe("fit-content(260px) minmax(48px, 1fr) max-content");
    expect(rows("Without places")[0].children).toHaveLength(3);
  });

  it("keeps a row in line when it lacks a place or gap that others have", () => {
    const items: RankBarItem[] = [DRIVERS[0], { id: "tbc", label: "Seat TBC", value: 0, color: rc.dim }];
    render(<RankBars items={items} label="Mixed" />);

    const [, tbc] = rows("Mixed");
    expect(tbc.children).toHaveLength(5);
    expect(tbc).toHaveTextContent("Seat TBC0");
  });

  it("shows the caller's figure, or the number, and a dash for a missing one", () => {
    const items: RankBarItem[] = [
      ...RISK,
      { id: "big", label: "Big number", value: 1234, color: rc.dim },
      { id: "missing", label: "No figure", value: Number.NaN, color: rc.dim },
    ];
    render(<RankBars items={items} label="Figures" />);

    const [bottas, , big, missing] = rows("Figures");
    expect(bottas).toHaveTextContent("36%");
    expect(big).toHaveTextContent("1,234");
    expect(missing).toHaveTextContent("No figure—");
    expect(fillOf(missing)).toHaveStyle({ width: "0%" });
  });

  it("scales against a caller's maximum", () => {
    render(<RankBars items={RISK} label="Risk" max={40} />);
    expect(fillOf(rows("Risk")[0])).toHaveStyle({ width: "90%" });
  });

  it("brings one row forward: it keeps its colour and is marked current, the rest go grey", () => {
    render(<RankBars items={DRIVERS} label="Points" highlight="verstappen" />);

    const [leader, second] = rows("Points");
    expect(second).toHaveAttribute("aria-current", "true");
    expect(second).toHaveClass("text-rc-ink");
    expect(fillOf(second)).toHaveStyle({ backgroundColor: "#3671c6" });

    expect(leader).not.toHaveAttribute("aria-current");
    expect(leader).toHaveClass("text-rc-ink-3");
    expect(fillOf(leader)).toHaveStyle({ backgroundColor: rc.dim });
  });

  it("marks no row and greys none without a highlight", () => {
    render(<RankBars items={DRIVERS} label="Points" />);
    for (const row of rows("Points")) {
      expect(row).not.toHaveAttribute("aria-current");
      expect(row).toHaveClass("text-rc-ink");
    }
  });

  it("draws the thicker constructors' bar on request, with row dividers and the caller's class", () => {
    render(<RankBars items={RISK} label="Teams" size="large" className="mt-4" />);

    const list = screen.getByRole("list", { name: "Teams" });
    expect(list).toHaveClass("mt-4", "grid", "gap-x-3");
    const [first] = rows("Teams");
    expect(first).toHaveClass("grid-cols-subgrid", "col-span-full", "min-h-8.5", "border-rc-line-soft");
    expect(fillOf(first).parentElement).toHaveClass("h-3.5");
  });
});
