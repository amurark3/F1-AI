import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLiveTiming } from "@/app/hooks/useLiveTiming";
import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, OVERVIEW_SEGMENTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import RaceControlHome, { metadata } from "./page";

const raceControl = vi.hoisted(() => ({ getOverviewSegment: vi.fn() }));

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/hooks/useLiveTiming", () => ({ useLiveTiming: vi.fn() }));
vi.mock("@/app/lib/server/raceControl", () => ({ ...raceControl, currentSeason: () => 2026 }));

const SEGMENTS = ["shell", "strategy", "predictions", "weather", "circuit"] as const;

describe("the Command Center page", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    vi.mocked(useLiveTiming).mockReturnValue({ positions: [], sessionStatus: null, isConnected: false });
    raceControl.getOverviewSegment.mockImplementation((_year: number, path: string) =>
      Promise.resolve(OVERVIEW_SEGMENTS_2026[path.slice(1) as (typeof SEGMENTS)[number]]),
    );
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      ...SEGMENTS.map((segment) =>
        http.get(apiUrl(`/api/race-control/overview/2026/${segment}`), () =>
          HttpResponse.json(OVERVIEW_SEGMENTS_2026[segment]),
        ),
      ),
    );
  });

  it("awaits nothing and hands each slot its segment's seed", async () => {
    let page: ReturnType<typeof RaceControlHome> | Promise<unknown> | undefined;
    await act(() => {
      page = RaceControlHome();
      renderWithProviders(page);
      return Promise.resolve();
    });

    expect(page).not.toBeInstanceOf(Promise);
    for (const segment of SEGMENTS) expect(raceControl.getOverviewSegment).toHaveBeenCalledWith(2026, `/${segment}`);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(OVERVIEW_SEGMENTS_2026.shell.race?.name ?? "");
  });

  it("keeps its title", () => {
    expect(metadata.title).toBe("Race Weekend Command Center | F1 AI");
  });
});
