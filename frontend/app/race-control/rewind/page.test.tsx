import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, SEASON_2026 } from "@/test/fixtures";
import { REWIND_R19 } from "@/test/fixtures/rewind";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import RewindPage, { metadata } from "./page";

const raceControl = vi.hoisted(() => ({ getSchedule: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/race-control/rewind",
}));
vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/lib/server/raceControl", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ...raceControl,
  currentSeason: () => 2026,
}));

describe("the Race Rewind page", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    raceControl.getSchedule.mockResolvedValue(SEASON_2026.schedule);
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(apiUrl("/api/schedule/2026"), () => HttpResponse.json(SEASON_2026.schedule)),
      http.get(apiUrl("/api/champions/2026"), () => HttpResponse.json(SEASON_2026.winners)),
      http.get(apiUrl("/api/race-control/rewind/2026/20"), () => HttpResponse.json({ ...REWIND_R19, round: 20 })),
    );
  });

  it("awaits nothing, and shows the picker and the latest completed race from the seeded schedule", async () => {
    let page: ReturnType<typeof RewindPage> | Promise<unknown> | undefined;
    await act(() => {
      page = RewindPage();
      renderWithProviders(page);
      return Promise.resolve();
    });

    expect(page).not.toBeInstanceOf(Promise);
    expect(raceControl.getSchedule).toHaveBeenCalledWith(2026);
    expect(await screen.findByRole("group", { name: "2026 race picker" })).toBeInTheDocument();
    expect(await screen.findByText(/^Race Rewind · Round 20 · /)).toBeInTheDocument();
  });

  it("says no rewind exists before any race has run", async () => {
    const upcoming = SEASON_2026.schedule.map((race) => ({ ...race, status: "upcoming" }));
    raceControl.getSchedule.mockResolvedValue(upcoming);
    server.use(http.get(apiUrl("/api/schedule/2026"), () => HttpResponse.json(upcoming)));
    await act(() => {
      renderWithProviders(RewindPage());
      return Promise.resolve();
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Race Rewind" })).toBeInTheDocument();
    expect(screen.getByText("The first rewind appears once a race of the season is classified.")).toBeInTheDocument();
  });

  it("keeps its title and describes the page", () => {
    expect(metadata.title).toBe("F1 Race Rewind | F1 AI");
    expect(metadata.description).toContain("Replay any Grand Prix lap by lap");
  });
});
