import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, OVERVIEW_SEGMENTS_2026, STANDINGS_PROGRESSION_2026, TEAMS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import StandingsPage, { metadata } from "./page";

const raceControl = vi.hoisted(() => ({
  getTeams: vi.fn(),
  getOverviewSegment: vi.fn(),
  getStandingsProgression: vi.fn(),
}));

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/lib/server/raceControl", () => ({ ...raceControl, currentSeason: () => 2026 }));

describe("the Standings page", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    raceControl.getTeams.mockResolvedValue(TEAMS_2026);
    raceControl.getOverviewSegment.mockResolvedValue(OVERVIEW_SEGMENTS_2026.shell);
    raceControl.getStandingsProgression.mockResolvedValue(STANDINGS_PROGRESSION_2026);
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(apiUrl("/api/race-control/teams/2026"), () => HttpResponse.json(TEAMS_2026)),
      http.get(apiUrl("/api/race-control/overview/2026/shell"), () => HttpResponse.json(OVERVIEW_SEGMENTS_2026.shell)),
      http.get(apiUrl("/api/race-control/standings/2026/progression"), () =>
        HttpResponse.json(STANDINGS_PROGRESSION_2026),
      ),
    );
  });

  it("awaits nothing and hands the sections their seeds", async () => {
    let page: ReturnType<typeof StandingsPage> | Promise<unknown> | undefined;
    await act(() => {
      page = StandingsPage();
      renderWithProviders(page);
      return Promise.resolve();
    });

    expect(page).not.toBeInstanceOf(Promise);
    expect(raceControl.getOverviewSegment).toHaveBeenCalledWith(2026, "/shell");
    expect(raceControl.getStandingsProgression).toHaveBeenCalledWith(2026);
    expect(await screen.findByRole("heading", { level: 1, name: "Kimi Antonelli" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Drivers' championship points" })).toBeInTheDocument();
  });

  it("keeps its title and mentions the title race in the description", () => {
    expect(metadata.title).toBe("F1 Championship Standings | F1 AI");
    expect(metadata.description).toContain("title race round by round");
  });
});
