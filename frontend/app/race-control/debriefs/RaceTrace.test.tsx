import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { RaceTrace } from "./RaceTrace";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const LAPS = DEBRIEF_R19.laps;

describe("RaceTrace", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("titles the neutralisations and draws five lines, the bands and the red flag", () => {
    const { container } = renderWithProviders(<RaceTrace laps={LAPS} />);

    expect(
      screen.getByRole("heading", { name: "A VSC, 2 Safety Cars and a red flag after lap 45" }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll("svg path")).toHaveLength(5);
    expect(container.querySelectorAll("svg rect")).toHaveLength(3);
    expect(screen.getByText("RED FLAG · L45")).toBeInTheDocument();
    expect(screen.getByText("Gap to the leader at each line crossing, top five · capped at 30 s")).toBeInTheDocument();
  });

  it("keys the legend to the podium, the rest and the neutralisations", async () => {
    renderWithProviders(<RaceTrace laps={LAPS} />);

    const legend = screen.getByRole("list", { name: "Race trace" });
    expect(await within(legend).findByText("Verstappen")).toBeInTheDocument();
    expect(within(legend).getByText("Leclerc, Norris")).toBeInTheDocument();
    expect(within(legend).getByText("VSC / Safety Car")).toBeInTheDocument();
    expect(within(legend).getByText("Red flag")).toBeInTheDocument();
  });

  it("gives the same numbers as a table for a screen reader", () => {
    renderWithProviders(<RaceTrace laps={LAPS} />);

    const table = screen.getByRole("table");
    expect(within(table).getByRole("row", { name: /^VER/ })).toBeInTheDocument();
    expect(within(table).getAllByRole("columnheader")).toHaveLength(72);
  });

  it("is quiet about neutralisations a race did not have, and marks a missing gap", () => {
    const [first, ...others] = LAPS.trace;
    const laps = {
      ...LAPS,
      neutralisations: [],
      trace: [{ ...first, gaps: first.gaps.map(() => null) }, ...others.slice(0, 1)],
    };
    renderWithProviders(<RaceTrace laps={laps} />);

    expect(screen.getByRole("heading", { name: "No Safety Car, VSC or red flag" })).toBeInTheDocument();
    expect(screen.queryByText("VSC / Safety Car")).not.toBeInTheDocument();
    expect(screen.queryByText("Red flag")).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("names a driver the entry list lacks by its code", () => {
    renderWithProviders(<RaceTrace laps={{ ...LAPS, drivers: [] }} />);

    expect(screen.getByRole("list", { name: "Race trace" })).toHaveTextContent("VER");
  });

  it("gives the reason when there is no trace", () => {
    renderWithProviders(<RaceTrace laps={{ ...LAPS, available: false, reason: "No laps yet." }} />);
    expect(screen.getByText("No laps yet.")).toBeInTheDocument();
  });

  it("says so when the trace is empty without a reason", () => {
    renderWithProviders(<RaceTrace laps={{ ...LAPS, trace: [], reason: null }} />);
    expect(screen.getByText("No race trace for this race.")).toBeInTheDocument();
  });
});
