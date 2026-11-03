import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { CIRCUIT_RECORDS, DIRECTORY_2026, SAO_PAULO_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { CircuitHistoryPanel } from "./CircuitHistoryPanel";

import type { CircuitRecord, OverviewCircuit } from "./weekendTypes";

// Entity links read the directory for the calendar year, so match any season.
const DIRECTORY_URL = apiUrl("/api/profiles/:year/directory");

function recordOf(circuit: OverviewCircuit): CircuitRecord {
  if (!circuit.record) throw new Error("no record in the captured circuit");
  return circuit.record;
}

const INTERLAGOS = recordOf(SAO_PAULO_2026.circuit);

function editions(): HTMLElement[] {
  return within(screen.getByRole("list")).getAllByRole("listitem");
}

/** The "from P…" chip of an edition row. */
function gridChip(row: HTMLElement): HTMLElement | null {
  return within(row).queryByTitle(/^Started P/);
}

describe("CircuitHistoryPanel", () => {
  beforeEach(() => {
    server.use(http.get(DIRECTORY_URL, () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("rates Interlagos' pole-to-win record and lists its last six winners", async () => {
    const { container } = renderWithProviders(<CircuitHistoryPanel record={INTERLAGOS} />);

    expect(screen.getByRole("heading", { name: "History" })).toBeInTheDocument();
    expect(screen.getByText("won from pole in the last 10 races here").previousElementSibling).toHaveTextContent(
      "6/10",
    );
    expect(container.querySelectorAll("circle")[1]).toHaveAttribute("stroke-dashoffset", "40");
    expect(editions().map((row) => row.textContent)).toEqual([
      "2025Lando Norrisfrom P1",
      "2024Max Verstappenpole Norrisfrom P17",
      "2023Max Verstappenfrom P1",
      "2022George Russellpole Magnussenfrom P1",
      "2021Lewis Hamiltonpole Bottasfrom P10",
      "2019Max Verstappenfrom P1",
    ]);
    expect(await within(editions()[0]).findByRole("link", { name: "Lando Norris" })).toHaveAttribute(
      "href",
      "/race-control/drivers/lando-norris",
    );
  });

  it("colours the winner's grid slot: pole green, a comeback from sixth or lower orange", () => {
    renderWithProviders(<CircuitHistoryPanel record={INTERLAGOS} />);
    const [fromPole, fromSeventeenth, , , fromTenth] = editions();

    expect(gridChip(fromPole)).toHaveStyle({ color: "#00FF78" });
    expect(gridChip(fromSeventeenth)).toHaveStyle({ color: "#FF8000" });
    expect(gridChip(fromTenth)).toHaveStyle({ color: "#FF8000" });
  });

  it("leaves a win from the front rows white: Mexico City", () => {
    renderWithProviders(<CircuitHistoryPanel record={CIRCUIT_RECORDS.mexicoCity2026} />);
    const fromThird = editions()[2];

    expect(fromThird).toHaveTextContent("2023Max Verstappenpole Leclercfrom P3");
    expect(gridChip(fromThird)).toHaveStyle({ color: "#F4F6FA" });
  });

  it("names this season's drivers who have won here, with their wins", async () => {
    renderWithProviders(<CircuitHistoryPanel record={INTERLAGOS} />);

    const grid = screen.getByText("On the grid:").parentElement;
    expect(grid).toHaveTextContent("On the grid:Verstappen×3Hamilton×3Norris×1");
    // The chip links the surname alone; the edition rows link the full name.
    expect(await screen.findByRole("link", { name: "Hamilton" })).toHaveAttribute(
      "href",
      "/race-control/drivers/lewis-hamilton",
    );
  });

  it("calls out nobody at Imola 2020, and links only winners who race this season", async () => {
    renderWithProviders(<CircuitHistoryPanel record={CIRCUIT_RECORDS.imola2020} />);

    expect(editions()[0]).toHaveTextContent("2006Michael Schumacherfrom P1");
    expect(screen.queryByText("On the grid:")).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Fernando Alonso" })).toHaveAttribute(
      "href",
      "/race-control/drivers/fernando-alonso",
    );
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("says Madring has no earlier Grand Prix", () => {
    renderWithProviders(<CircuitHistoryPanel record={CIRCUIT_RECORDS.madring2026.record} />);

    expect(screen.getByText("This is the circuit's first Grand Prix.")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("says when the circuit segment had no record", () => {
    renderWithProviders(<CircuitHistoryPanel record={undefined} />);

    expect(screen.getByText("Circuit history is unavailable right now.")).toBeInTheDocument();
  });

  it("copes with a race f1db lists without a winner or pole sitter", () => {
    // f1db names both for every race it holds, but the backend's `_edition` sends null for
    // either one a race lacks, and counts only editions with a pole sitter.
    const [first, ...rest] = INTERLAGOS.editions.map((edition) => ({ ...edition, pole: null, won_from_pole: false }));
    const record = {
      ...INTERLAGOS,
      pole_conversion: { wins_from_pole: 0, editions: 0 },
      editions: [{ ...first, winner: null }, ...rest],
    };
    const { container } = renderWithProviders(<CircuitHistoryPanel record={record} />);

    const [unclassified, comeback] = editions();
    expect(unclassified).toHaveTextContent(/^2025No classified winner$/);
    expect(unclassified.querySelector(".rounded-full")).toHaveStyle({ background: "#3A4254" });
    expect(gridChip(unclassified)).not.toBeInTheDocument();
    expect(comeback).toHaveTextContent(/^2024Max Verstappenfrom P17$/);
    expect(container.querySelectorAll("circle")[1]).toHaveAttribute("stroke-dashoffset", "100");
  });
});
