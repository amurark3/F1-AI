import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, STANDINGS_PROGRESSION_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { TitleRaceChart } from "./TitleRaceChart";

beforeEach(() => {
  server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
});

describe("TitleRaceChart", () => {
  it("titles itself from the data, with the clinch marker on the leader's line", async () => {
    const { container } = renderWithProviders(<TitleRaceChart progression={STANDINGS_PROGRESSION_2026} />);

    expect(
      await screen.findByRole("heading", { name: "Antonelli led from Suzuka and never gave it back" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Cumulative points by round · top 5")).toBeInTheDocument();
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(within(svg as unknown as HTMLElement).getByText("Clinched · R19 Mexico City")).toBeInTheDocument();
    expect(within(svg as unknown as HTMLElement).getByText("ANT 380")).toBeInTheDocument();
    expect(screen.getByText("Clinched after round 19, Mexico City.")).toBeInTheDocument();
  });

  it("gives screen readers the table: five drivers across 19 rounds", () => {
    renderWithProviders(<TitleRaceChart progression={STANDINGS_PROGRESSION_2026} />);

    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(6);
    expect(within(table).getAllByRole("columnheader")).toHaveLength(20);
    const [, antonelli] = within(table).getAllByRole("row");
    expect(within(antonelli).getByRole("rowheader")).toHaveTextContent("Kimi Antonelli");
    expect(within(antonelli).getAllByRole("cell").at(-1)).toHaveTextContent("380");
  });

  it("shows a dash where a driver had no points yet", () => {
    const [first] = STANDINGS_PROGRESSION_2026.drivers.entrants;
    const progression = {
      ...STANDINGS_PROGRESSION_2026,
      drivers: {
        ...STANDINGS_PROGRESSION_2026.drivers,
        entrants: [{ ...first, points: first.points.map(() => null) }],
      },
    };
    renderWithProviders(<TitleRaceChart progression={progression} />);

    expect(within(screen.getByRole("table")).getAllByRole("cell")[0]).toHaveTextContent("—");
  });

  it("has no marker, and says the leader has led since, while the title is open", async () => {
    const open = {
      ...STANDINGS_PROGRESSION_2026,
      drivers: { ...STANDINGS_PROGRESSION_2026.drivers, clinched: null },
    };
    renderWithProviders(<TitleRaceChart progression={open} />);

    expect(await screen.findByRole("heading", { name: "Antonelli has led since Suzuka" })).toBeInTheDocument();
    expect(screen.queryByText(/Clinched/)).not.toBeInTheDocument();
  });

  it("flags a provisional last round", () => {
    const rounds = STANDINGS_PROGRESSION_2026.rounds.map((r) => ({ ...r, provisional: r.round === 19 }));
    renderWithProviders(<TitleRaceChart progression={{ ...STANDINGS_PROGRESSION_2026, rounds }} />);

    expect(screen.getByText("Cumulative points by round · top 5 · round 19 provisional")).toBeInTheDocument();
  });

  it("says so before any round has paid points", () => {
    const empty = { ...STANDINGS_PROGRESSION_2026, rounds: [], as_of_round: null };
    renderWithProviders(<TitleRaceChart progression={empty} />);

    expect(screen.getByText("Title race")).toBeInTheDocument();
    expect(screen.getByText("No round has paid points yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
