import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, POWER_UNITS_2026, TEAMS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { PowerUnitsView } from "./PowerUnitsView";

import type { PowerUnitsSeeds } from "./usePowerUnits";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
    http.get(apiUrl("/api/race-control/power-units/2026"), () => HttpResponse.json(POWER_UNITS_2026 as never)),
    http.get(apiUrl("/api/race-control/teams/2026"), () => HttpResponse.json(TEAMS_2026)),
  );
});

describe("PowerUnitsView", () => {
  it("renders the hero, the matrix and the ranking from their seeds", async () => {
    const seeds: PowerUnitsSeeds = {
      powerUnits: Promise.resolve(POWER_UNITS_2026),
      teams: Promise.resolve(TEAMS_2026),
    };
    await act(() => {
      renderWithProviders(<PowerUnitsView year={2026} seeds={seeds} />);
      return Promise.resolve();
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Engines over the limit" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Allocation by car" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Who paid the most" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Power-unit grid-place penalties by car" })).toBeInTheDocument();
  });

  it("holds the h1 and skeletons while the seeds are pending", () => {
    const never = new Promise<never>(() => undefined);
    const { container } = renderWithProviders(
      <PowerUnitsView year={2026} seeds={{ powerUnits: never, teams: never }} />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Power units" })).toBeInTheDocument();
    expect(container.querySelectorAll("[class*='animate-pulse']").length).toBe(3);
  });
});
