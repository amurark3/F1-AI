import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { LapLeaders } from "./LapLeaders";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const LAPS = DEBRIEF_R19.laps;

describe("LapLeaders", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("draws one block per lap, with the red flag after its lap, and says who led", async () => {
    const { container } = renderWithProviders(<LapLeaders laps={LAPS} />);

    expect(await screen.findByRole("heading", { name: "Verstappen led from lap 44 to the flag" })).toBeInTheDocument();
    expect(container.querySelectorAll("[aria-hidden=true] > .contents > .flex-1")).toHaveLength(71);
    expect(container.querySelectorAll("[data-red-flag]")).toHaveLength(1);
    const legend = screen.getByRole("list", { name: "Lap leaders" });
    expect(within(legend).getByText("Red flag after lap 45")).toBeInTheDocument();
    expect(within(legend).getByText("Leclerc")).toBeInTheDocument();
  });

  it("lists the runs for a screen reader", () => {
    renderWithProviders(<LapLeaders laps={LAPS} />);

    expect(screen.getByText("Laps 28–43: Kimi Antonelli")).toBeInTheDocument();
  });

  it("draws laps with no leader dim and no flag rule when there was no red flag", () => {
    const laps = { ...LAPS, leaders: ["LEC", null], neutralisations: [] };
    const { container } = renderWithProviders(<LapLeaders laps={laps} />);

    expect(container.querySelectorAll("[data-red-flag]")).toHaveLength(0);
    expect(screen.queryByText(/Red flag/)).not.toBeInTheDocument();
    expect(screen.getByText(/1 lap without timing/)).toBeInTheDocument();
  });

  it("names a leader the entry list lacks by its code", () => {
    renderWithProviders(<LapLeaders laps={{ ...LAPS, drivers: [], leaders: ["ZZZ"] }} />);

    expect(screen.getByRole("heading", { name: "ZZZ led every lap" })).toBeInTheDocument();
  });

  it("gives the reason when OpenF1 has no laps", () => {
    renderWithProviders(
      <LapLeaders laps={{ ...LAPS, available: false, reason: "OpenF1 hasn't published this race's laps yet." }} />,
    );

    expect(screen.getByText("OpenF1 hasn't published this race's laps yet.")).toBeInTheDocument();
  });
});
