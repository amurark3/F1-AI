import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { SEASON_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import TelemetryLabPage, { metadata } from "./page";

const raceControl = vi.hoisted(() => ({ getSchedule: vi.fn() }));

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/lib/server/raceControl", () => ({ ...raceControl, currentSeason: () => 2026 }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/race-control/telemetry",
}));

describe("the Telemetry Lab page", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    raceControl.getSchedule.mockResolvedValue(SEASON_2026.schedule);
    server.use(http.get(apiUrl("/api/schedule/2026"), () => HttpResponse.json(SEASON_2026.schedule)));
  });

  it("awaits nothing and hands the lab the calendar", async () => {
    let page: ReturnType<typeof TelemetryLabPage> | Promise<unknown> | undefined;
    await act(() => {
      page = TelemetryLabPage();
      renderWithProviders(page);
      return Promise.resolve();
    });

    expect(page).not.toBeInstanceOf(Promise);
    expect(raceControl.getSchedule).toHaveBeenCalledWith(2026);
    expect(screen.getByRole("heading", { level: 1, name: "Telemetry Lab" })).toBeInTheDocument();
    expect(await screen.findByRole("group", { name: "2026 race picker" })).toBeInTheDocument();
  });

  it("keeps its title", () => {
    expect(metadata.title).toBe("Telemetry Lab | F1 AI");
  });
});
