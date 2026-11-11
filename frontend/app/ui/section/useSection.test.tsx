import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import useSWR from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState, type ServerStatus } from "@/app/hooks/useServerStatus";
import { fetcher } from "@/app/utils/fetcher";
import { SAO_PAULO_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { TestProviders } from "@/test/render";

import { RESTARTING_REASON, UNREACHABLE_REASON } from "./sectionState";
import { useSection } from "./useSection";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const URL = apiUrl("/api/race-control/overview/2026/shell");
/** The São Paulo shell segment, as the Command Center reads it. */
const SHELL = { year: 2026, race: SAO_PAULO_2026.race, stakes: SAO_PAULO_2026.stakes };
/** What `client_error` answers with when a segment cannot be built. */
const HANDLED_FAILURE = { year: 2026, error: "Something went wrong loading this data. Try again shortly." };
const SERVER_ERROR = "Request failed: 500 Internal Server Error";

/** The readiness probe's verdict; the hook reads only the status. */
function probe(status: ServerStatus): void {
  vi.mocked(useServerStatus).mockReturnValue({ status } as ServerState);
}

function answer(body: Record<string, unknown>): void {
  server.use(http.get(URL, () => HttpResponse.json(body)));
}

function fail(): void {
  server.use(http.get(URL, () => new HttpResponse(null, { status: 500 })));
}

function renderSection(seed: object | null = null) {
  return renderHook(() => useSection(URL, { seed, config: { revalidateOnFocus: false } }), { wrapper: TestProviders });
}

/** Waits for every fetch to land, so the state read next is where the section settles. */
async function settled(result: { current: { refreshing: boolean } }): Promise<void> {
  await waitFor(() => expect(result.current.refreshing).toBe(false));
}

describe("useSection", () => {
  beforeEach(() => probe("ready"));

  it("is pending until the first answer, then ready with it", async () => {
    answer(SHELL);
    const { result } = renderSection();

    expect(result.current).toMatchObject({ status: "pending", data: undefined, reason: null, refreshing: true });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current).toMatchObject({ data: SHELL, reason: null, refreshing: false });
  });

  it("fails with the server's answer when the first fetch fails and there is no data", async () => {
    fail();
    const { result } = renderSection();

    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current).toMatchObject({ data: undefined, reason: SERVER_ERROR });
  });

  it("names a dropped connection in words", async () => {
    server.use(http.get(URL, () => HttpResponse.error()));
    const { result } = renderSection();

    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current.reason).toBe(UNREACHABLE_REASON);
  });

  it("treats a handled backend failure (200 with an error) as a failure, not data", async () => {
    answer(HANDLED_FAILURE);
    const { result } = renderSection();

    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current).toMatchObject({ data: undefined, reason: HANDLED_FAILURE.error });
  });

  it("keeps the server's seed when the browser's refresh fails: stale, not failed", async () => {
    fail();
    const { result } = renderSection(SHELL);

    // The seed paints at once, while the refresh runs behind it.
    expect(result.current).toMatchObject({ status: "ready", data: SHELL });
    await waitFor(() => expect(result.current.status).toBe("stale"));
    expect(result.current).toMatchObject({ data: SHELL, reason: SERVER_ERROR });
  });

  it("keeps fetched data when a later refresh fails, and is ready again once one lands", async () => {
    answer(SHELL);
    const { result } = renderSection();
    await waitFor(() => expect(result.current.status).toBe("ready"));

    fail();
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe("stale"));
    expect(result.current).toMatchObject({ data: SHELL, reason: SERVER_ERROR });

    answer(SHELL);
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.reason).toBeNull();
  });

  it("retries a failed section on request, refreshing while it asks", async () => {
    fail();
    const { result } = renderSection();
    await waitFor(() => expect(result.current.status).toBe("failed"));

    answer(SHELL);
    act(() => result.current.retry());
    expect(result.current.refreshing).toBe(true);
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.data).toEqual(SHELL);
  });

  it("drops a seed that carries an error and fetches for itself", async () => {
    answer(SHELL);
    const { result } = renderSection(HANDLED_FAILURE);

    expect(result.current).toMatchObject({ status: "pending", data: undefined });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.data).toEqual(SHELL);
  });

  it("reads an error payload another hook cached under the same key as a failure", async () => {
    // The Race Control sidebar fetches the shell with the plain fetcher, which
    // stores a handled failure as data. The section must not show it as data.
    answer(HANDLED_FAILURE);
    const { result } = renderHook(
      () => {
        useSWR<unknown, Error>(URL, fetcher);
        return useSection(URL);
      },
      { wrapper: TestProviders },
    );

    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current).toMatchObject({ data: undefined, reason: HANDLED_FAILURE.error });
  });

  describe("while the server restarts", () => {
    beforeEach(() => probe("warming"));

    it("stays pending on a failure rather than calling it a fault", async () => {
      fail();
      const { result } = renderSection();
      await settled(result);

      expect(result.current).toMatchObject({ status: "pending", reason: null });
    });

    it("keeps data on screen, and says why it is not fresh", async () => {
      fail();
      const { result } = renderSection(SHELL);

      await waitFor(() => expect(result.current.status).toBe("stale"));
      expect(result.current).toMatchObject({ data: SHELL, reason: RESTARTING_REASON });
    });

    it("fetches again as soon as the server is ready", async () => {
      fail();
      const { result, rerender } = renderSection();
      await settled(result);
      expect(result.current.status).toBe("pending");

      answer(SHELL);
      probe("ready");
      rerender();
      await waitFor(() => expect(result.current.status).toBe("ready"));
      expect(result.current.data).toEqual(SHELL);
    });

    it("does not fetch again on readiness when nothing failed", async () => {
      const requests = vi.fn();
      server.use(
        http.get(URL, () => {
          requests();
          return HttpResponse.json(SHELL);
        }),
      );
      const { result, rerender } = renderSection();
      await waitFor(() => expect(result.current.status).toBe("ready"));

      probe("ready");
      rerender();
      await settled(result);
      expect(requests).toHaveBeenCalledTimes(1);
    });
  });
});
