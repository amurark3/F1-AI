import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { TeamHeatGrid } from "./TeamHeatGrid";

const { mercedes, red_bull: redBull } = PROFILE_PAGES_2026;

function rowOf(name: RegExp): HTMLElement {
  const row = screen.getAllByRole("row").find((item) => name.test(item.textContent ?? ""));
  if (!row) throw new Error(`no row ${name}`);
  return row;
}

describe("TeamHeatGrid", () => {
  it("is a table of every driver by every round of the season", () => {
    render(<TeamHeatGrid profile={mercedes} />);

    const table = screen.getByRole("table", { name: "Mercedes race results by round" });
    const headers = within(table).getAllByRole("columnheader");
    expect(headers.map((header) => header.textContent)).toEqual([
      "Driver",
      ...Array.from({ length: 23 }, (_, i) => `R${i + 1}`),
    ]);
    expect(within(table).getAllByRole("rowheader")).toHaveLength(2);
    expect(table.parentElement).toHaveClass("overflow-x-auto");
  });

  it("marks the last completed round's header, and no other", () => {
    render(<TeamHeatGrid profile={mercedes} />);

    expect(screen.getByRole("columnheader", { name: "R20" })).toHaveClass("text-rc-ink");
    expect(screen.getByRole("columnheader", { name: "R19" })).toHaveClass("text-rc-ink-3");
  });

  it("reads Antonelli's R7 and Russell's R16 as DNF, never the place f1db classified", () => {
    render(<TeamHeatGrid profile={mercedes} />);

    const ant = within(rowOf(/Antonelli/)).getAllByRole("cell");
    expect(ant[6]).toHaveTextContent("DNF");
    expect(ant[6]).toHaveTextContent("R7 Barcelona-Catalunya GP: retired (Electrical), classified P16 · 0 pts");
    expect(ant[6]).not.toHaveTextContent(/^16/);
    const rus = within(rowOf(/Russell/)).getAllByRole("cell");
    expect(rus[15]).toHaveTextContent("DNF");
    expect(rus[15]?.querySelector("span")?.firstChild?.textContent).toBe("DNF");
  });

  it("reads Verstappen's R9 as DNF with its reason, and no cell prints 20", () => {
    render(<TeamHeatGrid profile={redBull} />);

    const ver = within(rowOf(/Verstappen/)).getAllByRole("cell");
    expect(ver[8]).toHaveTextContent("DNF");
    expect(ver[8]?.querySelector("[title]")?.getAttribute("title")).toContain("Spun off");
    const visible = [...document.querySelectorAll("tbody td > span:not(.sr-only)")].map(
      (cell) => cell.firstChild?.textContent,
    );
    expect(visible).not.toContain("20");
  });

  it("colours the podium by place and leaves a driver's other rounds absent", () => {
    render(<TeamHeatGrid profile={redBull} />);

    const law = within(rowOf(/Lawson/)).getAllByRole("cell");
    expect(law[0]).toHaveTextContent("did not race for Red Bull");
    expect(law[11]).toHaveTextContent("7");
    const ant = within(rowOf(/Verstappen/)).getAllByRole("cell");
    const classes = ant.map((cell) => cell.querySelector("span")?.className ?? "");
    expect(classes.some((value) => value.includes("bg-rc-gold"))).toBe(true);
  });

  it("says rounds still to run are future", () => {
    render(<TeamHeatGrid profile={mercedes} />);

    const cells = within(rowOf(/Antonelli/)).getAllByRole("cell");
    expect(cells[22]).toHaveTextContent("R23 Abu Dhabi GP: still to run");
    expect(cells[22]?.querySelector("span")?.className).toContain("border-dashed");
  });

  it("colours a podium finish gold, silver and bronze and a points finish with the team tint", () => {
    render(<TeamHeatGrid profile={mercedes} />);

    const cells = within(rowOf(/Antonelli/)).getAllByRole("cell");
    const look = (index: number) => cells[index]?.querySelector("span") as HTMLElement;
    expect(look(0).className).toContain("bg-rc-silver");
    expect(look(1).className).toContain("bg-rc-gold");
    expect(look(7).className).toContain("bg-rc-bronze");
    expect(look(14).style.backgroundColor).toContain("color-mix");
    expect(look(8).className).toContain("bg-rc-ink/3");
  });

  it("keys the cells", () => {
    render(<TeamHeatGrid profile={mercedes} />);

    const legend = screen.getByRole("list", { name: "Heat grid key" });
    expect(
      within(legend)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["Win", "P2", "P3", "Points", "Did not finish or start", "Still to run"]);
  });
});
