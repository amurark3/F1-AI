import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { scheduleRaces } from "@/app/lib/server/raceControl";
import { DIRECTORY_2026, SEASON_2026 } from "@/test/fixtures";
import { DEBRIEF_R19, DEBRIEF_RADIO_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import DebriefsPage, { metadata } from "./page";

const raceControl = vi.hoisted(() => ({ getSchedule: vi.fn(), getDebrief: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/race-control/debriefs",
}));
vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/lib/server/raceControl", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ...raceControl,
  currentSeason: () => 2026,
}));

describe("the Debriefs page", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    raceControl.getSchedule.mockResolvedValue(SEASON_2026.schedule);
    raceControl.getDebrief.mockResolvedValue({ ...DEBRIEF_R19.summary, round: 20 });
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(apiUrl("/api/schedule/2026"), () => HttpResponse.json(SEASON_2026.schedule)),
      http.get(apiUrl("/api/champions/2026"), () => HttpResponse.json(SEASON_2026.winners)),
      http.get(apiUrl("/api/race-control/debrief/2026/20"), () =>
        HttpResponse.json({ ...DEBRIEF_R19.summary, round: 20 }),
      ),
      http.get(apiUrl("/api/race-control/debrief/2026/20/laps"), () => HttpResponse.json(DEBRIEF_R19.laps)),
      http.get(apiUrl("/api/race-control/debrief/2026/20/penalties"), () => HttpResponse.json(DEBRIEF_R19.penalties)),
      http.get(apiUrl("/api/race-control/debrief/2026/20/overtakes"), () => HttpResponse.json(DEBRIEF_R19.overtakes)),
      http.get(apiUrl("/api/race-control/debrief/2026/20/radio"), () => HttpResponse.json(DEBRIEF_RADIO_R19)),
    );
  });

  it("awaits nothing, and seeds the latest completed round's summary", async () => {
    let page: ReturnType<typeof DebriefsPage> | Promise<unknown> | undefined;
    await act(() => {
      page = DebriefsPage();
      renderWithProviders(page);
      return Promise.resolve();
    });

    expect(page).not.toBeInstanceOf(Promise);
    expect(raceControl.getSchedule).toHaveBeenCalledWith(2026);
    expect(await screen.findByText("Race debrief · Round 20 · Mexican Grand Prix")).toBeInTheDocument();
    expect(raceControl.getDebrief).toHaveBeenCalledWith(2026, 20);
    expect(scheduleRaces(SEASON_2026.schedule)).toHaveLength(23);
  });

  it("seeds nothing from a backend that still serves the old debrief, or none at all", async () => {
    for (const served of [{ podium: [], takeaways: [] }, null]) {
      raceControl.getDebrief.mockResolvedValue(served);
      const { unmount } = await act(() => {
        const view = renderWithProviders(DebriefsPage());
        return Promise.resolve(view);
      });
      expect(await screen.findByText("Race debrief · Round 20 · Mexican Grand Prix")).toBeInTheDocument();
      unmount();
    }
  });

  it("asks for no debrief before any race has run", async () => {
    raceControl.getDebrief.mockClear();
    const upcoming = SEASON_2026.schedule.map((race) => ({ ...race, status: "upcoming" }));
    raceControl.getSchedule.mockResolvedValue(upcoming);
    server.use(http.get(apiUrl("/api/schedule/2026"), () => HttpResponse.json(upcoming)));
    await act(() => {
      renderWithProviders(DebriefsPage());
      return Promise.resolve();
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Debrief" })).toBeInTheDocument();
    expect(raceControl.getDebrief).not.toHaveBeenCalled();
  });

  it("keeps its title and describes every section", () => {
    expect(metadata.title).toBe("F1 Race Debriefs | F1 AI");
    expect(metadata.description).toContain("lap leaders, race trace, grid to finish, penalties");
  });
});
