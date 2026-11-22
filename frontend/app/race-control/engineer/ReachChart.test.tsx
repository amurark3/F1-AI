import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { ReachChart } from "./ReachChart";

import type { ReachChartData } from "./engineerModel";

/** The mockup's fight for second after round 19 (four races, no sprint: 100 points on offer), cut to three rows. */
const DRIVERS: ReachChartData = {
  kind: "reach",
  title: "3 drivers can still finish second · points after round 19 → most possible",
  championship: "drivers",
  year: 2026,
  rows: [
    { key: "VER", name: "Max Verstappen", team: "Red Bull", points: 261, max: 361 },
    { key: "HAM", name: "Lewis Hamilton", team: "Ferrari", points: 259, max: 359 },
    { key: "NOR", name: "Lando Norris", team: "McLaren", points: 221, max: 321 },
  ],
};

describe("ReachChart", () => {
  beforeEach(() => {
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("captions the figure with its computed title and lists every row, today against the most possible", async () => {
    renderWithProviders(<ReachChart chart={DRIVERS} />);

    expect(screen.getByRole("figure")).toHaveTextContent(DRIVERS.title);
    const rows = within(screen.getByRole("list", { name: DRIVERS.title })).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(await screen.findByText("Verstappen")).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent("261 → 361");
    expect(rows[2]).toHaveTextContent("221 → 321");
  });

  it("colours each bar by team and draws the dashed run to the most possible", () => {
    const { container } = renderWithProviders(<ReachChart chart={DRIVERS} />);

    const fills = container.querySelectorAll<HTMLElement>("[data-fill]");
    expect(fills[0]).toHaveStyle({ backgroundColor: "#3671C6", width: "72.3%" });
    expect(fills[1]).toHaveStyle({ backgroundColor: "#E8002D" });
    const runs = container.querySelectorAll<HTMLElement>("[data-reach]");
    expect(runs).toHaveLength(3);
    expect(runs[0]).toHaveClass("border-dashed");
  });

  it("names teams as teams, and a row with no team gets the neutral colour; half points print", () => {
    const chart: ReachChartData = {
      kind: "reach",
      title: "2 teams can still win the title · points after round 19 → most possible",
      championship: "constructors",
      year: 2026,
      rows: [
        { key: "Mercedes", name: "Mercedes", team: "Mercedes", points: 630, max: 802 },
        { key: "Unlisted", name: "Unlisted", team: "", points: 12.5, max: 112.5 },
      ],
    };
    const { container } = renderWithProviders(<ReachChart chart={chart} />);

    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Mercedes");
    expect(rows[1]).toHaveTextContent("12.5 → 112.5");
    const fills = container.querySelectorAll<HTMLElement>("[data-fill]");
    expect(fills[0]).toHaveStyle({ backgroundColor: "#27F4D2" });
    expect(fills[1]).toHaveStyle({ backgroundColor: "#6B7280" });
  });
});
