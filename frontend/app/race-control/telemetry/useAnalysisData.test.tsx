import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { apiUrl, server } from "@/test/msw/server";
import { TestProviders } from "@/test/render";

import { useComparison, useDegradation, useLapList, useTrackMap, useWeekend } from "./useAnalysisData";

const OK = { available: true, pending: false };

function seen(path: string, body: object = OK): URL[] {
  const urls: URL[] = [];
  server.use(
    http.get(apiUrl(path), ({ request }) => {
      urls.push(new URL(request.url));
      return HttpResponse.json(body);
    }),
  );
  return urls;
}

describe("the analysis hooks", () => {
  it("read a weekend's sessions, and nothing without a round", async () => {
    const urls = seen("/api/analysis/2026/20/sessions");
    const idle = renderHook(() => useWeekend(2026, null), { wrapper: TestProviders });
    expect(idle.result.current).toEqual({ data: undefined, error: undefined, loading: false });

    const { result } = renderHook(() => useWeekend(2026, 20), { wrapper: TestProviders });
    await waitFor(() => {
      expect(result.current.data).toEqual(OK);
    });
    expect(result.current.loading).toBe(false);
    expect(urls).toHaveLength(1);
  });

  it("ask for a session's laps only once there is a round and a session", async () => {
    const urls = seen("/api/analysis/2026/20/laps");
    const wait = renderHook(() => useLapList(2026, 20, null), { wrapper: TestProviders });
    expect(wait.result.current.data).toBeUndefined();
    const { result } = renderHook(() => useLapList(2026, 20, "Q"), { wrapper: TestProviders });
    await waitFor(() => {
      expect(result.current.data).toEqual(OK);
    });
    expect(urls.map((url) => url.search)).toEqual(["?session=Q"]);
  });

  it("ask for a track map with the lap and part left out when null", async () => {
    const urls = seen("/api/analysis/2026/20/track-map");
    const noDriver = renderHook(() => useTrackMap(2026, 20, { session: "Q", driver: null, lap: null, segment: null }), {
      wrapper: TestProviders,
    });
    expect(noDriver.result.current.data).toBeUndefined();

    const bare = renderHook(() => useTrackMap(2026, 20, { session: "Q", driver: "ANT", lap: null, segment: null }), {
      wrapper: TestProviders,
    });
    await waitFor(() => {
      expect(bare.result.current.data).toEqual(OK);
    });
    const full = renderHook(() => useTrackMap(2026, 20, { session: "Q", driver: "ANT", lap: 14, segment: 3 }), {
      wrapper: TestProviders,
    });
    await waitFor(() => {
      expect(full.result.current.data).toEqual(OK);
    });
    expect(urls.map((url) => url.search).sort()).toEqual(
      ["?session=Q&driver=ANT&lap=14&segment=3", "?session=Q&driver=ANT"].sort(),
    );
  });

  it("compare two different drivers only", async () => {
    const urls = seen("/api/analysis/2026/20/compare");
    const same = renderHook(() => useComparison(2026, 20, { session: "Q", a: "ANT", b: "ANT", segment: null }), {
      wrapper: TestProviders,
    });
    expect(same.result.current.data).toBeUndefined();
    const { result } = renderHook(() => useComparison(2026, 20, { session: "Q", a: "ANT", b: "RUS", segment: 2 }), {
      wrapper: TestProviders,
    });
    await waitFor(() => {
      expect(result.current.data).toEqual(OK);
    });
    expect(urls.map((url) => url.search)).toEqual(["?session=Q&a=ANT&b=RUS&segment=2"]);
  });

  it("read tyre degradation for a race session", async () => {
    const urls = seen("/api/analysis/2026/20/tyre-degradation");
    const wait = renderHook(() => useDegradation(2026, null, "R"), { wrapper: TestProviders });
    expect(wait.result.current.data).toBeUndefined();
    const { result } = renderHook(() => useDegradation(2026, 20, "R"), { wrapper: TestProviders });
    await waitFor(() => {
      expect(result.current.data).toEqual(OK);
    });
    expect(urls.map((url) => url.search)).toEqual(["?session=R"]);
  });

  it("surfaces a failed request as an error, not as loading", async () => {
    server.use(http.get(apiUrl("/api/analysis/2026/20/sessions"), () => new HttpResponse(null, { status: 500 })));
    const { result } = renderHook(() => useWeekend(2026, 20), { wrapper: TestProviders });
    await waitFor(() => {
      expect(result.current.error).toBeDefined();
    });
    expect(result.current.loading).toBe(false);
  });

  it("keeps a pending answer on screen while it waits to ask again", async () => {
    seen("/api/analysis/2026/20/sessions", { available: false, pending: true });
    const { result } = renderHook(() => useWeekend(2026, 20), { wrapper: TestProviders });
    await waitFor(() => {
      expect(result.current.data?.pending).toBe(true);
    });
  });
});
