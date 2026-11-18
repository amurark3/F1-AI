import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { SEASON_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { TestProviders } from "@/test/render";

import { resolveRound, useHubSections, useSeasonContext } from "./useHubShell";

import type { GrandPrixSeed } from "./hubSeed";
import type { HubUrl } from "./useHubUrlState";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const MEXICO = SEASON_2026.schedule.find((race) => race.round === 19)!;
const DRIVERS = { drivers: [{ driver_code: "VER", driver_name: "Max Verstappen", team: "Red Bull" }] };
const DRIVERS_URL = apiUrl("/api/race-control/drivers/2026");
const SCHEDULE_URL = apiUrl("/api/schedule/2026");

function url(changes: Partial<HubUrl> = {}): HubUrl {
  return { round: null, tab: null, view: null, update: vi.fn(), ...changes };
}

function seedOf(changes: Partial<GrandPrixSeed> = {}): GrandPrixSeed {
  return {
    year: 2026,
    schedule: null,
    drivers: null,
    snapshots: { pre_qualifying: null, post_qualifying: null },
    snapshotRound: null,
    grid: null,
    sessions: null,
    strategy: null,
    ...changes,
  };
}

describe("resolveRound", () => {
  it("takes the selected round, and the default for one the calendar does not hold", () => {
    expect(resolveRound(SEASON_2026.schedule, 2, MEXICO).effectiveRound).toBe(2);
    expect(resolveRound(SEASON_2026.schedule, 99, MEXICO).effectiveRound).toBe(19);
    expect(resolveRound(SEASON_2026.schedule, null, MEXICO).selectedRace).toBe(MEXICO);
  });

  it("has no round when there is nothing to fall back on", () => {
    expect(resolveRound([], null, null)).toEqual({ effectiveRound: null, selectedRace: null });
  });
});

describe("useHubSections", () => {
  it("opens every round on Weekend, a finished one too, and its prediction on the review", () => {
    const { result } = renderHook(() => useHubSections(url(), MEXICO));
    expect(result.current.activeTab).toBe("weekend");
    expect(result.current.predictionView).toBe("review");
  });

  it("prefers the URL's tab and view over the weekend's progress", () => {
    const { result } = renderHook(() => useHubSections(url({ tab: "grid", view: "risk" }), MEXICO));
    expect(result.current.activeTab).toBe("grid");
    expect(result.current.predictionView).toBe("risk");
  });

  it("asks for stints only once Stints has been opened, and keeps asking", () => {
    let hubUrl = url();
    const { result, rerender } = renderHook(() => useHubSections(hubUrl, MEXICO));
    expect(result.current.stintsWanted).toBe(false);

    hubUrl = url({ tab: "stints" });
    rerender();
    expect(result.current.stintsWanted).toBe(true);

    hubUrl = url({ tab: "grid" });
    rerender();
    expect(result.current.stintsWanted).toBe(true);
  });

  it("writes tab and view changes to the URL", () => {
    const hubUrl = url();
    const { result } = renderHook(() => useHubSections(hubUrl, MEXICO));
    act(() => result.current.onSelectTab("results"));
    act(() => result.current.onSelectView("order"));
    expect(hubUrl.update).toHaveBeenNthCalledWith(1, { tab: "results" });
    expect(hubUrl.update).toHaveBeenNthCalledWith(2, { tab: "predictions", view: "order" });
  });
});

describe("useSeasonContext", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(SCHEDULE_URL, () => HttpResponse.json(SEASON_2026.schedule as never)));
  });

  function render(seed = seedOf()) {
    return renderHook(() => useSeasonContext(seed), { wrapper: TestProviders });
  }

  it("fills the calendar and the entry list in as each arrives", async () => {
    server.use(http.get(DRIVERS_URL, () => HttpResponse.json(DRIVERS)));
    const { result } = render();

    expect(result.current.schedulePending).toBe(true);
    expect(result.current.drivers).toEqual([]);
    await waitFor(() => expect(result.current.drivers).toEqual(DRIVERS.drivers));
    await waitFor(() => expect(result.current.schedule).toHaveLength(SEASON_2026.schedule.length));
    expect(result.current.driversFailed).toBe(false);
  });

  it("keeps the calendar on screen while the entry list fails, and retries it in place", async () => {
    let calls = 0;
    server.use(
      http.get(DRIVERS_URL, () => {
        calls += 1;
        return calls === 1 ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(DRIVERS);
      }),
    );
    const { result } = render(seedOf({ schedule: SEASON_2026.schedule }));

    expect(result.current.schedulePending).toBe(false);
    await waitFor(() => expect(result.current.driversFailed).toBe(true));
    // The calendar never left: a failing entry list does not take the page down.
    expect(result.current.schedule).toHaveLength(SEASON_2026.schedule.length);
    expect(result.current.scheduleFailed).toBe(false);

    act(() => result.current.reloadDrivers());
    await waitFor(() => expect(result.current.drivers).toEqual(DRIVERS.drivers));
    expect(result.current.driversFailed).toBe(false);
    expect(typeof result.current.reloadSchedule).toBe("function");
  });
});
