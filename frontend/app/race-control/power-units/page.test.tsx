import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, POWER_UNITS_2026, TEAMS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import PowerUnitsPage, { metadata } from "./page";

const raceControl = vi.hoisted(() => ({ getPowerUnits: vi.fn(), getTeams: vi.fn() }));

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/lib/server/raceControl", () => ({ ...raceControl, currentSeason: () => 2026 }));

describe("the Power Units page", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    raceControl.getPowerUnits.mockResolvedValue(POWER_UNITS_2026);
    raceControl.getTeams.mockResolvedValue(TEAMS_2026);
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(apiUrl("/api/race-control/power-units/2026"), () => HttpResponse.json(POWER_UNITS_2026 as never)),
      http.get(apiUrl("/api/race-control/teams/2026"), () => HttpResponse.json(TEAMS_2026)),
    );
  });

  it("awaits nothing and hands the sections their seeds", async () => {
    let page: ReturnType<typeof PowerUnitsPage> | Promise<unknown> | undefined;
    await act(() => {
      page = PowerUnitsPage();
      renderWithProviders(page);
      return Promise.resolve();
    });

    expect(page).not.toBeInstanceOf(Promise);
    expect(raceControl.getPowerUnits).toHaveBeenCalledWith(2026);
    expect(raceControl.getTeams).toHaveBeenCalledWith(2026);
    expect(await screen.findByRole("heading", { level: 1, name: "Engines over the limit" })).toBeInTheDocument();
  });

  it("keeps its title", () => {
    expect(metadata.title).toBe("Power Unit Tracker | F1 AI");
  });
});
