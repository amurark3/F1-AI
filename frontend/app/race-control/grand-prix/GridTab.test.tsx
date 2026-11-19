import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, GRIDS_2026, WEEKEND_SESSIONS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { GridTab } from "./GridTab";

import type { StartingGridResponse } from "./gridModel";
import type { WeekendSessionsResponse } from "./sessionsModel";

function show(grid: StartingGridResponse | undefined, sessions?: WeekendSessionsResponse, round: number | null = 19) {
  return renderWithProviders(
    <GridTab grid={grid} loading={false} sessions={sessions} round={round} raceName="Mexico City Grand Prix" />,
  );
}

describe("GridTab", () => {
  beforeEach(() => {
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("puts the pit-lane starter in the pit-lane box, never in a numbered slot", () => {
    show(GRIDS_2026.mexicoCityOfficial, WEEKEND_SESSIONS_2026.mexicoCity);

    expect(screen.getByRole("heading", { name: "3 penalties on the grid" })).toBeInTheDocument();
    const lawson = screen.getByText("Pit lane", { selector: "p" }).parentElement!;
    expect(within(lawson).getByText("Liam Lawson")).toBeInTheDocument();
    expect(within(lawson).getByText("Pit lane", { selector: "span" })).toHaveClass("text-rc-red-text");
    expect(within(lawson).getByText("DSQ")).toBeInTheDocument();
    expect(screen.queryByText("P22")).not.toBeInTheDocument();
  });

  it("drops 'Qualified Pn' from cars that started where they qualified", () => {
    show(GRIDS_2026.mexicoCityOfficial, WEEKEND_SESSIONS_2026.mexicoCity);

    // Only Antonelli (P5 to P4) and Verstappen (P4 to P5) moved.
    expect(screen.getAllByText(/^Qualified P\d+$/)).toHaveLength(2);
    expect(screen.getByText(/\+1 promoted by VER’s drop/)).toHaveClass("text-rc-gain");
  });

  it("marks Bottas's -50 as having cost nothing, and lists the penalties applied", () => {
    show(GRIDS_2026.mexicoCityOfficial, WEEKEND_SESSIONS_2026.mexicoCity);

    const penalties = screen.getByText("Penalties applied").closest("section")!;
    expect(within(penalties).getByText("−50 places · cost nothing, already at the back")).toBeInTheDocument();
    expect(within(penalties).getByText("−1 place")).toBeInTheDocument();
    expect(within(penalties).getByText("Pit lane")).toBeInTheDocument();
  });

  it("replaces 'from the grid to the flag' with links to Results and the Debrief", () => {
    show(GRIDS_2026.mexicoCityOfficial);

    expect(screen.getByRole("link", { name: "Results" })).toHaveAttribute(
      "href",
      "/race-control/grand-prix?round=19&tab=results",
    );
    expect(screen.getByRole("link", { name: "Debrief" })).toHaveAttribute("href", "/race-control/debriefs?round=19");
    expect(screen.queryByText(/grid to the flag/i)).not.toBeInTheDocument();
  });

  it("drops the Results link when no round is selected", () => {
    show(GRIDS_2026.mexicoCityOfficial, undefined, null);

    expect(screen.queryByRole("link", { name: "Results" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Debrief" })).toBeInTheDocument();
  });

  it("shows each penalty's FIA reason and document on the slot and in the penalties panel", () => {
    show(GRIDS_2026.mexicoCityWithFiaReasons);

    const penalties = screen.getByText("Penalties applied").closest("section")!;
    expect(within(penalties).getByText("Causing a collision \u00b7 doc 33")).toBeInTheDocument();
    expect(screen.getAllByText("Causing a collision \u00b7 doc 33")).toHaveLength(2);
    expect(screen.getByText(/reasons: FIA decisions 17, 33, 34, 58, 65/)).toBeInTheDocument();
  });

  it("labels the FIA's provisional grid provisional, with its penalties applied", () => {
    show(GRIDS_2026.mexicoCityFiaProvisional);

    expect(screen.getByRole("heading", { name: "3 penalties on the grid" })).toBeInTheDocument();
    expect(screen.getByText(/FIA provisional starting grid \(doc 60\)/)).toBeInTheDocument();
    expect(screen.queryByText(/Penalties cannot be listed yet/)).not.toBeInTheDocument();
  });

  it("labels a Jolpica qualifying order provisional, with its source, and applies no penalty", () => {
    show(GRIDS_2026.saoPauloJolpicaProvisional);

    expect(screen.getByRole("heading", { name: "Qualifying order, before any penalty" })).toBeInTheDocument();
    expect(screen.getByText("Provisional")).toBeInTheDocument();
    expect(screen.getByText(/jolpica-qualifying\), provisional/)).toBeInTheDocument();
    expect(screen.getByText(/Penalties cannot be listed yet/)).toBeInTheDocument();
  });

  it("says plainly when no grid exists, and when no penalty was applied", () => {
    const { unmount } = show(GRIDS_2026.lasVegasNone);
    expect(screen.getByText("The grid is not set yet")).toBeInTheDocument();
    expect(screen.getByText(/Penalties are not known for this round yet/)).toBeInTheDocument();
    unmount();

    const none = show(undefined);
    expect(screen.getByText(/appears here once qualifying has run/)).toBeInTheDocument();
    none.unmount();

    show({ ...GRIDS_2026.mexicoCityOfficial, penalties: [] });
    expect(screen.getByText(/No grid penalties were applied/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Every car starts where it qualified" })).toBeInTheDocument();
  });

  it("fills the empty half of a row with a placeholder box", () => {
    const grid = GRIDS_2026.mexicoCityOfficial.grid;
    const odd = { ...GRIDS_2026.mexicoCityOfficial, grid: grid.slice(0, 3) };
    const { container, unmount } = show(odd);
    expect(container.querySelectorAll(".border-dashed.rounded-sm").length).toBe(1);
    unmount();

    const second = show({ ...odd, grid: grid.slice(1, 2) });
    expect(second.container.querySelectorAll(".border-dashed.rounded-sm").length).toBe(1);
  });

  it("switches to the sprint's grid on a sprint weekend", async () => {
    const { user } = show(GRIDS_2026.mexicoCityOfficial, WEEKEND_SESSIONS_2026.sprintWeekend);
    const group = screen.getByRole("radiogroup", { name: "Grid" });

    await user.click(within(group).getByRole("radio", { name: "Sprint" }));
    expect(screen.getByText("Starting grid · Mexico City Grand Prix sprint")).toBeInTheDocument();

    await user.click(within(group).getByRole("radio", { name: "Grand Prix" }));
    expect(screen.getByText("Starting grid · Mexico City Grand Prix")).toBeInTheDocument();
  });

  it("offers no switch without a sprint, and shows a loader while reading", () => {
    const { unmount } = show(GRIDS_2026.mexicoCityOfficial, WEEKEND_SESSIONS_2026.mexicoCity);
    expect(screen.queryByRole("radiogroup", { name: "Grid" })).not.toBeInTheDocument();
    unmount();

    renderWithProviders(<GridTab loading sessions={undefined} round={19} raceName="x" />);
    expect(screen.getByText("Loading the starting grid")).toBeInTheDocument();
  });
});
