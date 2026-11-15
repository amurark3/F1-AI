import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse, type JsonBodyType } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { SEASON_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { TestProviders } from "@/test/render";

import { useRaceWinners, useSchedule } from "./useSchedule";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const SCHEDULE_URL = apiUrl("/api/schedule/2026");
const WINNERS_URL = apiUrl("/api/champions/2026");
/** What `client_error` answers with when the calendar cannot be built. */
const HANDLED_FAILURE = { error: "Something went wrong loading this data. Try again shortly." };

/** Answers the calendar with `body`, counting the requests. */
function answerSchedule(body: JsonBodyType): { count: () => number } {
  let requests = 0;
  server.use(
    http.get(SCHEDULE_URL, () => {
      requests += 1;
      return HttpResponse.json(body);
    }),
  );
  return { count: () => requests };
}

describe("useSchedule", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  });

  it("is pending until the calendar arrives, then lists its rounds", async () => {
    answerSchedule(SEASON_2026.schedule);
    const { result } = renderHook(() => useSchedule(2026), { wrapper: TestProviders });

    expect(result.current).toMatchObject({ races: [], pending: true, failed: false });
    await waitFor(() => expect(result.current.races).toHaveLength(23));
    expect(result.current).toMatchObject({ pending: false, failed: false });
  });

  it("asks once for every reader of the same season", async () => {
    const requests = answerSchedule(SEASON_2026.schedule);
    const { result } = renderHook(() => [useSchedule(2026), useSchedule(2026), useSchedule(2026)], {
      wrapper: TestProviders,
    });

    await waitFor(() => expect(result.current.every((schedule) => schedule.races.length === 23)).toBe(true));
    expect(requests.count()).toBe(1);
  });

  it("shows the server render's calendar at once", () => {
    answerSchedule(SEASON_2026.schedule);
    const { result } = renderHook(() => useSchedule(2026, SEASON_2026.schedule), { wrapper: TestProviders });

    expect(result.current).toMatchObject({ races: SEASON_2026.schedule, pending: false });
  });

  it("drops a server render that failed, and fetches for itself", async () => {
    answerSchedule(SEASON_2026.schedule);
    const { result } = renderHook(() => useSchedule(2026, HANDLED_FAILURE), { wrapper: TestProviders });

    expect(result.current.pending).toBe(true);
    await waitFor(() => expect(result.current.races).toHaveLength(23));
  });

  it("fails when the calendar cannot be loaded, and loads it on a retry", async () => {
    answerSchedule(HANDLED_FAILURE);
    const { result } = renderHook(() => useSchedule(2026), { wrapper: TestProviders });

    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.races).toEqual([]);

    answerSchedule(SEASON_2026.schedule);
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.races).toHaveLength(23));
    expect(result.current.failed).toBe(false);
  });
});

describe("useRaceWinners", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  });

  it("is undefined until the season's winners arrive", async () => {
    server.use(http.get(WINNERS_URL, () => HttpResponse.json(SEASON_2026.winners)));
    const { result } = renderHook(() => useRaceWinners(2026), { wrapper: TestProviders });

    expect(result.current).toBeUndefined();
    await waitFor(() => expect(result.current).toHaveLength(20));
    expect(result.current?.[18]).toMatchObject({ round: 19, winner: "Max Verstappen", team: "Red Bull" });
  });

  it("stays undefined when they cannot be loaded", async () => {
    let answered = false;
    server.use(
      http.get(WINNERS_URL, () => {
        answered = true;
        return new HttpResponse(null, { status: 500 });
      }),
    );
    const { result } = renderHook(() => useRaceWinners(2026), { wrapper: TestProviders });

    await waitFor(() => expect(answered).toBe(true));
    expect(result.current).toBeUndefined();
  });
});
