import { act, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Suspense } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, POWER_UNITS_2026, TEAMS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { AllocationMatrix } from "./AllocationMatrix";

import type { PowerUnitsSeeds } from "./usePowerUnits";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const ORDER = [12, 63, 44, 16, 3, 6, 1, 81, 30, 41, 10, 43, 87, 51, 5, 27, 55, 23, 14, 18, 77, 11];

async function renderMatrix(powerUnits: unknown = POWER_UNITS_2026, teams: unknown = TEAMS_2026, teamsStatus = 200) {
  server.use(
    http.get(apiUrl("/api/race-control/power-units/2026"), () => HttpResponse.json(powerUnits as never)),
    http.get(apiUrl("/api/race-control/teams/2026"), () =>
      HttpResponse.json((teams ?? {}) as never, { status: teamsStatus }),
    ),
  );
  const seeds = {
    powerUnits: Promise.resolve(powerUnits),
    teams: Promise.resolve(teams),
  } as unknown as PowerUnitsSeeds;
  await act(() => {
    renderWithProviders(
      <Suspense fallback={null}>
        <AllocationMatrix year={2026} seeds={seeds} />
      </Suspense>,
    );
    return Promise.resolve();
  });
}

function rows(): HTMLElement[] {
  return within(screen.getByRole("table")).getAllByRole("row").slice(1);
}

function numbers(): number[] {
  return rows().map((row) => Number(/^#(\d+)/.exec(within(row).getByRole("rowheader").textContent ?? "")?.[1]));
}

function rowFor(number: number): HTMLElement {
  return rows()[numbers().indexOf(number)];
}

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
});

describe("AllocationMatrix", () => {
  it("lists all 22 cars in constructors' order", async () => {
    await renderMatrix();

    expect(
      screen.getByRole("table", { name: "Power-unit elements used by all 22 cars against the 2026 allocation" }),
    ).toBeInTheDocument();
    expect(numbers()).toEqual(ORDER);
    expect(screen.getByText("In constructors' championship order")).toBeInTheDocument();
  });

  it("tags the three shared seats and shows a stand-in's own number", async () => {
    await renderMatrix();

    expect(within(screen.getByRole("table")).getAllByText("Shared seat")).toHaveLength(3);
    expect(within(within(rowFor(6)).getByRole("rowheader")).getByText("#30")).toBeInTheDocument();
  });

  it("labels the over-allocation weekends with no ruling", async () => {
    await renderMatrix();

    expect(rowFor(14)).toHaveTextContent("no ruling found");
    expect(rowFor(30)).toHaveTextContent("no ruling found");
    expect(rowFor(12)).not.toHaveTextContent("no ruling found");
  });

  it("links each row to its car page", async () => {
    await renderMatrix();

    expect(within(rowFor(5)).getByRole("link")).toHaveAttribute("href", "/race-control/power-units/5");
  });

  it("explains the marks", async () => {
    await renderMatrix();

    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).getByText("Used within the allocation")).toBeInTheDocument();
    expect(within(legend).getByText("Still available")).toBeInTheDocument();
    expect(within(legend).getByText("Beyond the allocation (penalty)")).toBeInTheDocument();
    expect(screen.getByText(/more than one driver raced this car/)).toBeInTheDocument();
  });

  it("falls back to car-number order when the standings never load", async () => {
    await renderMatrix(POWER_UNITS_2026, null, 500);

    expect(screen.getByText("In car-number order: standings not loaded")).toBeInTheDocument();
    expect(numbers()).toEqual([...ORDER].sort((a, b) => a - b));
  });

  it("shows the table with no element columns when the payload lists none", async () => {
    await renderMatrix({ ...POWER_UNITS_2026, elements: undefined });

    expect(within(screen.getByRole("table")).getAllByRole("columnheader")).toHaveLength(2);
  });

  it("gives the reason when nothing is collected", async () => {
    await renderMatrix({ ...POWER_UNITS_2026, available: false, reason: "Not collected yet.", cars: [] });

    expect(screen.getByText("Not collected yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
