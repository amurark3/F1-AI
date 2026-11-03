import { render, screen, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SlopeChart, type SlopeItem } from "./SlopeChart";
import { SLOPE } from "./slopeLayout";
import { rc } from "./tokens";

/** Grid → finish, Mexico City 2026 (debrief.html), a few of the field. */
const MEXICO: SlopeItem[] = [
  { id: "ver", label: "VER", name: "Max Verstappen", start: 5, end: 1, color: "#3671c6" },
  { id: "ham", label: "HAM", name: "Lewis Hamilton", start: 1, end: 2, color: "#e8002d" },
  { id: "rus", label: "RUS", name: "George Russell", start: 2, end: 6, color: "#27f4d2" },
  { id: "law", label: "LAW", name: "Liam Lawson", start: 22, end: 7, startText: "PL", color: "#6692ff" },
  {
    id: "lin",
    label: "LIN",
    name: "Arvid Lindblad",
    start: 8,
    end: 18,
    endText: "DNF L58",
    incomplete: true,
    color: "#6692ff",
  },
];

/** Points before and after R19. */
const POINTS: SlopeItem[] = [
  { id: "ant", label: "ANT", start: 355, end: 380, color: "#27f4d2" },
  { id: "ver", label: "VER", start: 243, end: 261, color: "#3671c6" },
  { id: "pia", label: "PIA", start: 230, end: 230, color: "#ff8000" },
  { id: "nor", label: "NOR", start: 225, end: 221, color: "#ff8000" },
];

function chart(): SVGSVGElement {
  const svg = document.querySelector("svg");
  if (svg === null) throw new Error("no chart drawn");
  return svg;
}

function lineOf(id: string): Element {
  const group = chart().querySelector(`[data-line="${id}"]`);
  if (group === null) throw new Error(`no line for ${id}`);
  return group;
}

function pathOf(id: string): SVGPathElement {
  const path = lineOf(id).querySelector("path");
  if (path === null) throw new Error(`no path for ${id}`);
  return path;
}

function labelsOf(code: string): string[] {
  return [...chart().querySelectorAll("text")].map((text) => text.textContent).filter((text) => text.includes(code));
}

function tableRows(name: string): string[][] {
  const table = screen.getByRole("table", { name });
  return within(table)
    .getAllByRole("row")
    .map((row) => [...row.children].map((cell) => cell.textContent));
}

describe("SlopeChart", () => {
  it("draws a line per entity across the frame, hidden from assistive tech, under the column heads", () => {
    render(<SlopeChart items={MEXICO} label="Grid against finish" startLabel="Grid" endLabel="Finish" />);

    const svg = chart();
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("viewBox", `0 0 600 ${SLOPE.top + 21 * SLOPE.rowGap + SLOPE.bottom}`);
    expect(pathOf("ver")).toHaveAttribute("d", `M74 ${34 + 4 * 29.5} L486 34`);
    expect(lineOf("ver").querySelectorAll("circle")).toHaveLength(2);

    const heads = screen.getAllByText(/^(Grid|Finish)$/, { selector: "text" });
    expect(heads.map((head) => head.getAttribute("x"))).toEqual([String(SLOPE.xStart), String(SLOPE.xEnd)]);
    expect(heads[0].parentElement).toHaveClass("uppercase", "fill-rc-ink-3");
  });

  it("labels both ends with the code and the figure, and the change with its sign", () => {
    render(<SlopeChart items={MEXICO} label="Grid against finish" startLabel="Grid" endLabel="Finish" />);

    expect(labelsOf("VER")).toEqual(["VER P5", "P1 VER +4"]);
    expect(labelsOf("RUS")).toEqual(["RUS P2", "P6 RUS −4"]);
    expect(labelsOf("LAW")).toEqual(["LAW PL", "P7 LAW +15"]);
  });

  it("colours places gained and lost, on top of the sign", () => {
    render(<SlopeChart items={MEXICO} label="Grid against finish" startLabel="Grid" endLabel="Finish" />);

    expect(screen.getByText("+4", { exact: false, selector: "tspan" })).toHaveClass("fill-rc-gain");
    expect(screen.getByText("−4", { exact: false, selector: "tspan" })).toHaveClass("fill-rc-red-text");
  });

  it("dashes a line that ended early, with no change figure, and keeps it grey", () => {
    render(<SlopeChart items={MEXICO} label="Grid against finish" startLabel="Grid" endLabel="Finish" />);

    expect(labelsOf("LIN")).toEqual(["LIN P8", "DNF L58 LIN"]);
    const path = pathOf("lin");
    expect(path).toHaveAttribute("stroke-dasharray", "4 4");
    expect(path).not.toHaveAttribute("pathLength");
    expect(path).toHaveAttribute("stroke", rc.dim);
    expect(path).toHaveClass("motion-safe:animate-overlay-in");
  });

  it("colours lines that changed by at least the emphasis, and greys the rest with quieter labels", () => {
    render(<SlopeChart items={MEXICO} label="Grid against finish" startLabel="Grid" endLabel="Finish" emphasis={3} />);

    expect(pathOf("ver")).toHaveAttribute("stroke", "#3671c6");
    expect(pathOf("ver")).toHaveAttribute("stroke-width", "3");
    expect(pathOf("ham")).toHaveAttribute("stroke", rc.dim);
    expect(pathOf("ham")).toHaveAttribute("stroke-width", "1.5");
    expect(lineOf("ham").querySelector("circle")).toHaveAttribute("fill", rc.dim);

    expect(labelsOf("HAM")).toEqual(["HAM P1", "P2 HAM"]);
    const hamLabel = screen.getByText("HAM P1", { selector: "text" });
    expect(hamLabel).toHaveClass("fill-rc-ink-3");
    expect(screen.getByText("VER P5", { selector: "text" })).toHaveClass("fill-rc-ink");
  });

  it("draws grey lines first, so the coloured ones sit on top", () => {
    render(<SlopeChart items={MEXICO} label="Grid against finish" startLabel="Grid" endLabel="Finish" emphasis={3} />);

    const order = [...chart().querySelectorAll("[data-line]")].map((group) => group.getAttribute("data-line"));
    expect(order).toEqual(["ham", "lin", "ver", "rus", "law"]);
  });

  it("follows an entity's own highlight over the emphasis rule", () => {
    const items: SlopeItem[] = [
      { ...MEXICO[0], highlight: false },
      { ...MEXICO[1], highlight: true },
      { ...MEXICO[4], highlight: true },
    ];
    render(<SlopeChart items={items} label="Grid against finish" startLabel="Grid" endLabel="Finish" emphasis={3} />);

    expect(pathOf("ver")).toHaveAttribute("stroke", rc.dim);
    expect(pathOf("ham")).toHaveAttribute("stroke", "#e8002d");
    expect(labelsOf("HAM")).toEqual(["HAM P1", "P2 HAM −1"]);
    // A highlighted retirement is coloured, but still has no change figure.
    expect(pathOf("lin")).toHaveAttribute("stroke", "#6692ff");
    expect(labelsOf("LIN")).toEqual(["LIN P8", "DNF L58 LIN"]);
  });

  it("draws solid lines in once behind motion-safe, so the server's HTML is the chart at rest", () => {
    const html = renderToString(
      <SlopeChart items={MEXICO} label="Grid against finish" startLabel="Grid" endLabel="Finish" className="mt-2" />,
    );
    expect(html).toContain("motion-safe:animate-track-draw");
    expect(html).not.toMatch(/(^|[\s"])animate-/);
    expect(html).toContain('class="mt-2"');

    render(<SlopeChart items={MEXICO} label="Grid against finish" startLabel="Grid" endLabel="Finish" />);
    expect(pathOf("ver")).toHaveAttribute("pathLength", "1");
    expect(pathOf("ver")).toHaveAttribute("stroke-dasharray", "1 1");
  });

  it("gives screen readers the data as a table, in words", () => {
    render(
      <SlopeChart items={MEXICO} label="Grid against finish" startLabel="Grid" endLabel="Finish" nameHeader="Driver" />,
    );

    expect(tableRows("Grid against finish")).toEqual([
      ["Driver", "Grid", "Finish", "Change"],
      ["Max Verstappen", "P5", "P1", "gained 4 places"],
      ["Lewis Hamilton", "P1", "P2", "lost 1 place"],
      ["George Russell", "P2", "P6", "lost 4 places"],
      ["Liam Lawson", "PL", "P7", "gained 15 places"],
      ["Arvid Lindblad", "P8", "DNF L58", "not compared"],
    ]);
    expect(screen.getByRole("table")).toHaveClass("sr-only");
  });

  it("reads values with the higher at the top, plain numbers and neutral change figures", () => {
    render(
      <SlopeChart items={POINTS} label="Points before and after R19" startLabel="R18" endLabel="R19" scale="value" />,
    );

    expect(labelsOf("ANT")).toEqual(["ANT 355", "380 ANT +25"]);
    expect(pathOf("ant").getAttribute("d")).toMatch(/L486 34$/);
    expect(screen.getByText("+25", { exact: false, selector: "tspan" })).toHaveClass("fill-rc-ink-2");
    expect(screen.getByText("−4", { exact: false, selector: "tspan" })).toHaveClass("fill-rc-ink-2");
    expect(labelsOf("PIA")).toEqual(["PIA 230", "230 PIA 0"]);
    expect(screen.getByText("0", { exact: false, selector: "tspan" })).toHaveClass("fill-rc-ink-3");

    expect(tableRows("Points before and after R19")).toEqual([
      ["Name", "R18", "R19", "Change"],
      ["ANT", "355", "380", "up 25"],
      ["VER", "243", "261", "up 18"],
      ["PIA", "230", "230", "no change"],
      ["NOR", "225", "221", "down 4"],
    ]);
  });

  it("leaves out an entity without both ends, and draws nothing with no entities", () => {
    const items: SlopeItem[] = [MEXICO[0], { id: "x", label: "XXX", start: Number.NaN, end: 3, color: rc.dim }];
    const { unmount } = render(<SlopeChart items={items} label="Partial" startLabel="Grid" endLabel="Finish" />);
    expect(labelsOf("XXX")).toEqual([]);
    expect(tableRows("Partial")).toHaveLength(2);
    unmount();

    const { container } = render(<SlopeChart items={[]} label="Empty" startLabel="Grid" endLabel="Finish" />);
    expect(container).toBeEmptyDOMElement();
  });
});
