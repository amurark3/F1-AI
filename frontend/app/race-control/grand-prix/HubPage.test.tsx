import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import {
  DIRECTORY_2026,
  GRIDS_2026,
  MEXICO_CITY_2026,
  PREDICTION_REVIEW_R19,
  RACE_RESULTS_2026,
  SAO_PAULO_2026,
  SEASON_2026,
  WEEKEND_SESSIONS_2026,
} from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { GrandPrixHub } from "./GrandPrixHub";
import { GrandPrixView } from "./GrandPrixView";
import GrandPrixHubPage from "./page";
import { DEFAULT_HUB_URL } from "./useHubUrlState";

import type { GrandPrixSeed } from "./hubSeed";

const nav = vi.hoisted(() => ({ search: "round=19&tab=predictions&view=order", replace: vi.fn() }));
const raceControl = vi.hoisted(() => ({
  getSchedule: vi.fn(),
  getDrivers: vi.fn(),
  getPredictionSnapshot: vi.fn(),
  getStartingGrid: vi.fn(),
  getWeekendSessions: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/race-control/grand-prix",
}));
vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/lib/server/raceControl", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ...raceControl,
  currentSeason: () => 2026,
}));

function seed(changes: Partial<GrandPrixSeed> = {}): GrandPrixSeed {
  return {
    year: 2026,
    schedule: SEASON_2026.schedule,
    drivers: { drivers: [] },
    snapshots: { pre_qualifying: null, post_qualifying: PREDICTION_REVIEW_R19 },
    snapshotRound: 19,
    grid: GRIDS_2026.mexicoCityOfficial,
    sessions: WEEKEND_SESSIONS_2026.mexicoCity,
    strategy: null,
    ...changes,
  };
}

describe("the Grand Prix hub", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    nav.replace.mockClear();
    nav.search = "round=19&tab=predictions&view=order";
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(apiUrl("/api/schedule/2026"), () => HttpResponse.json(SEASON_2026.schedule)),
      http.get(apiUrl("/api/champions/2026"), () => HttpResponse.json(SEASON_2026.winners)),
      http.get(apiUrl("/api/race-control/drivers/2026"), () => HttpResponse.json({ drivers: [] })),
      http.get(apiUrl("/api/race-control/grid/2026/:round"), () => HttpResponse.json(GRIDS_2026.mexicoCityOfficial)),
      http.get(apiUrl("/api/race-control/sessions/2026/:round"), () =>
        HttpResponse.json(WEEKEND_SESSIONS_2026.mexicoCity),
      ),
      http.get(apiUrl("/api/race-control/stints/2026/:round"), () => HttpResponse.json(MEXICO_CITY_2026.strategy)),
      http.get(apiUrl("/api/predictions/2026/:round/snapshot"), () => HttpResponse.json(PREDICTION_REVIEW_R19)),
      http.get(apiUrl("/api/race-control/results/2026/:round"), () => HttpResponse.json(RACE_RESULTS_2026.mexicoCity)),
      http.get(apiUrl("/api/race-control/circuit/2026/:round"), () => HttpResponse.json(MEXICO_CITY_2026.circuit)),
      http.get(apiUrl("/api/race-control/glance/2026/:round"), () => HttpResponse.json(MEXICO_CITY_2026.glance)),
      http.get(apiUrl("/api/race-control/overview/2026/shell"), () =>
        HttpResponse.json({
          race: SEASON_2026.schedule.find((race) => race.round === 19)!,
          stakes: SAO_PAULO_2026.stakes,
        }),
      ),
    );
  });

  it.each([
    ["weekend", /Mexico City/],
    ["grid", /penalties on the grid/],
    ["results", /Verstappen wins/],
  ] as const)("opens the %s section for the round in the URL", async (tab, heading) => {
    renderWithProviders(<GrandPrixView seed={seed()} url={{ ...DEFAULT_HUB_URL, round: 19, tab }} />);

    expect((await screen.findAllByText(heading))[0]).toBeVisible();
  });

  it("shows a placeholder while the calendar is still on its way", () => {
    server.use(http.get(apiUrl("/api/schedule/2026"), () => new Promise(() => undefined)));
    renderWithProviders(<GrandPrixView seed={seed({ schedule: null })} url={DEFAULT_HUB_URL} />);

    expect(document.querySelector("[class*='animate-pulse']")).toBeInTheDocument();
  });

  it("has no Results section without a round", () => {
    renderWithProviders(
      <GrandPrixView seed={seed({ schedule: [], snapshotRound: null })} url={{ ...DEFAULT_HUB_URL, tab: "results" }} />,
    );

    expect(screen.queryByText(/Verstappen wins/)).not.toBeInTheDocument();
  });

  it("reads the round and section from the URL and writes a change back to it", async () => {
    const { user } = renderWithProviders(<GrandPrixHub seed={seed()} />);

    expect(await screen.findByText("Predicted order · 22 cars")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Podium" }));

    expect(nav.replace).toHaveBeenCalledWith("/race-control/grand-prix?round=19&tab=predictions&view=podium", {
      scroll: false,
    });
  });

  it("drops the query when the selection is back to nothing", async () => {
    nav.search = "";
    const { user } = renderWithProviders(<GrandPrixHub seed={seed()} />);

    await user.click(await screen.findByRole("tab", { name: "Predictions" }));
    expect(nav.replace).toHaveBeenLastCalledWith("/race-control/grand-prix?tab=predictions", { scroll: false });
  });

  it("keeps the server render's selection inert until the URL can be read", () => {
    expect(DEFAULT_HUB_URL.update({ round: 19 })).toBeUndefined();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("links the Sessions tab to the Telemetry Lab for the round on screen", async () => {
    renderWithProviders(<GrandPrixView seed={seed()} url={{ ...DEFAULT_HUB_URL, round: 19, tab: "sessions" }} />);

    expect(await screen.findByRole("link", { name: /Speed maps and lap-by-lap comparisons/ })).toHaveAttribute(
      "href",
      "/race-control/telemetry?tab=map&round=19",
    );
  });

  it("loads the stints only once the Stints tab is opened, and links to the tyre lab", async () => {
    renderWithProviders(<GrandPrixView seed={seed()} url={{ ...DEFAULT_HUB_URL, round: 19, tab: "stints" }} />);

    expect(await screen.findByRole("link", { name: /Tyre degradation for this race/ })).toBeVisible();
    await waitFor(() => expect(screen.queryByText("Loading race strategy")).not.toBeInTheDocument());
  });

  it("says the strategy is loading while the stints are still on their way", async () => {
    server.use(http.get(apiUrl("/api/race-control/stints/2026/:round"), () => new Promise(() => undefined)));
    renderWithProviders(<GrandPrixView seed={seed()} url={{ ...DEFAULT_HUB_URL, round: 19, tab: "stints" }} />);

    expect(await screen.findByText("Loading race strategy")).toBeVisible();
  });

  it("offers no telemetry link before a round is known", () => {
    renderWithProviders(
      <GrandPrixView
        seed={seed({ schedule: [], snapshotRound: null })}
        url={{ ...DEFAULT_HUB_URL, tab: "sessions" }}
      />,
    );

    expect(screen.queryByRole("link", { name: /Speed maps/ })).not.toBeInTheDocument();
  });

  it("prefetches the default round's snapshots, grid and sessions on the server", async () => {
    raceControl.getSchedule.mockResolvedValue(SEASON_2026.schedule);
    raceControl.getDrivers.mockResolvedValue({ drivers: [] });
    raceControl.getPredictionSnapshot.mockResolvedValue(PREDICTION_REVIEW_R19);
    raceControl.getStartingGrid.mockResolvedValue(GRIDS_2026.mexicoCityOfficial);
    raceControl.getWeekendSessions.mockResolvedValue(WEEKEND_SESSIONS_2026.mexicoCity);

    render(await GrandPrixHubPage());

    await waitFor(() => expect(screen.getByRole("tab", { name: "Predictions" })).toBeVisible());
    expect(raceControl.getPredictionSnapshot).toHaveBeenCalledWith(2026, expect.any(Number), "pre_qualifying");
    expect(raceControl.getPredictionSnapshot).toHaveBeenCalledWith(2026, expect.any(Number), "post_qualifying");
  });

  it("prefetches nothing when the calendar is empty", async () => {
    raceControl.getSchedule.mockResolvedValue([]);
    raceControl.getDrivers.mockResolvedValue(null);
    raceControl.getPredictionSnapshot.mockClear();

    render(await GrandPrixHubPage());

    expect(raceControl.getPredictionSnapshot).not.toHaveBeenCalled();
  });
});
