import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { PREDICTION_REVIEW_R19, SEASON_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { TestProviders } from "@/test/render";

import { useHubUrlState } from "./useHubUrlState";
import { usePredictionWorkspace } from "./usePredictionWorkspace";

import type { GrandPrixSeed } from "./hubSeed";

const nav = vi.hoisted(() => ({ search: "round=19", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/race-control/grand-prix",
}));

const MEXICO = SEASON_2026.schedule.find((race) => race.round === 19)!;
const SEED: GrandPrixSeed = {
  year: 2026,
  schedule: SEASON_2026.schedule,
  drivers: null,
  snapshots: { pre_qualifying: null, post_qualifying: PREDICTION_REVIEW_R19 },
  snapshotRound: 19,
  grid: null,
  sessions: null,
  strategy: null,
};

function mount(round: number | null) {
  return renderHook(() => usePredictionWorkspace(SEED, round, round === null ? null : MEXICO), {
    wrapper: TestProviders,
  });
}

describe("usePredictionWorkspace", () => {
  it("ignores a run asked for with no round selected", () => {
    const post = vi.fn();
    server.use(http.post(apiUrl("/api/predictions/2026/:round/compute"), post));
    const { result } = mount(null);

    act(() => result.current.onRun());

    expect(post).not.toHaveBeenCalled();
    expect(result.current.isComputing).toBe(false);
  });

  it("joins a run already going rather than starting a second one", async () => {
    let release: () => void = () => undefined;
    const post = vi.fn(async () => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return HttpResponse.json(PREDICTION_REVIEW_R19);
    });
    server.use(http.post(apiUrl("/api/predictions/2026/:round/compute"), post));
    const { result } = mount(19);

    act(() => result.current.onRun());
    await waitFor(() => expect(result.current.isComputing).toBe(true));
    act(() => result.current.onRun());
    release();

    await waitFor(() => expect(result.current.isComputing).toBe(false));
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("names a failure that is not an Error", async () => {
    server.use(http.post(apiUrl("/api/predictions/2026/:round/compute"), () => HttpResponse.error()));
    vi.spyOn(globalThis, "fetch").mockRejectedValue("boom");
    const { result } = mount(19);

    act(() => result.current.onRun());

    await waitFor(() => expect(result.current.computeError).toBe("Prediction compute failed."));
  });
});

describe("useHubUrlState", () => {
  it("replaces the URL with the bare path when nothing is selected any more", () => {
    nav.search = "round=19";
    const { result } = renderHook(() => useHubUrlState());

    act(() => result.current.update({ round: null }));

    expect(nav.replace).toHaveBeenCalledWith("/race-control/grand-prix", { scroll: false });
  });
});
