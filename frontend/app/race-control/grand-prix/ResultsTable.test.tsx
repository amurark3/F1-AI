import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, RACE_RESULTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { ResultsTable } from "./ResultsTable";

const MEXICO = RACE_RESULTS_2026.mexicoCity.race!;

function rowOf(code: string): HTMLElement {
  const cell = screen.getAllByText(code).find((node) => node.closest("tr"));
  if (!cell) throw new Error(`no row for ${code}`);
  return cell.closest("tr") as HTMLElement;
}

describe("ResultsTable", () => {
  beforeEach(() => {
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("prints Mexico City's classification: winner time, gaps, penalties and points", async () => {
    renderWithProviders(<ResultsTable result={MEXICO} year={2026} />);

    expect(screen.getAllByRole("columnheader").map((head) => head.textContent)).toEqual([
      "Pos",
      "Driver",
      "Team",
      "Time / gap",
      "Pts",
    ]);
    const winner = await screen.findByRole("row", { name: /Verstappen/ });
    expect(within(winner).getByText("1")).toHaveClass("text-rc-gold");
    expect(within(winner).getByText("2:20:28.772")).toBeInTheDocument();
    expect(within(winner).getByText("25")).toBeInTheDocument();

    const second = rowOf("HAM");
    expect(within(second).getByText("+0.799")).toBeInTheDocument();
    expect(within(second).getByText("2")).not.toHaveClass("text-rc-gold");
    // Fastest lap is tagged on the driver who set it, and only there.
    expect(within(second).getByText("Fastest lap")).toBeInTheDocument();
    expect(screen.getAllByText("Fastest lap")).toHaveLength(1);

    const penalised = rowOf("PIA");
    expect(within(penalised).getByText("13")).toBeInTheDocument();
    expect(within(penalised).getByText("incl. +10 s · P7 on the road")).toBeInTheDocument();
    expect(within(rowOf("GAS")).getByText("incl. +30 s · P10 on the road")).toBeInTheDocument();
  });

  it("mutes a zero and keeps the team column to wide screens", () => {
    renderWithProviders(<ResultsTable result={MEXICO} year={2026} />);

    const zero = within(rowOf("ALB")).getByText("0");
    expect(zero).toHaveClass("text-rc-ink-3");
    expect(screen.getByRole("columnheader", { name: "Team" })).toHaveClass("max-sm:hidden");
  });

  it("puts the five retirements under a labelled cut, reading DNF and why, never a place", () => {
    renderWithProviders(<ResultsTable result={MEXICO} year={2026} />);

    const cut = screen.getByText("Did not finish");
    expect(screen.getAllByText("Did not finish")).toHaveLength(1);
    const rows = screen.getAllByRole("row");
    const lastFinisher = rows.findIndex((row) => row.contains(screen.getByText("+51.483")));
    expect(rows[lastFinisher + 1]).toContainElement(cut);

    const lindblad = rowOf("LIN");
    const dnf = within(lindblad).getByText("DNF");
    expect(dnf).toHaveClass("text-rc-red-text");
    expect(within(lindblad).getByText("Collision · 58 laps")).toHaveClass("text-rc-red-text");
    expect(within(rowOf("STR")).getByText("Engine · 5 laps")).toBeInTheDocument();
    // The Pos cell holds the word itself, not a place of 18-22.
    expect(within(lindblad).getAllByRole("cell")[0]).toHaveTextContent(/^DNF$/);
  });

  it("shows no cut when everyone finished, and a dash for points a source does not give", () => {
    const finishers = MEXICO.classification.slice(0, 3).map((row) => ({ ...row, points: null }));
    renderWithProviders(<ResultsTable result={{ ...MEXICO, classification: finishers }} year={2026} />);

    expect(screen.queryByText("Did not finish")).not.toBeInTheDocument();
    expect(within(rowOf("HAM")).getByText("—")).toBeInTheDocument();
  });
});
