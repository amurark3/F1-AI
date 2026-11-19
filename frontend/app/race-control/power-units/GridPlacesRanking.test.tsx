import { act, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Suspense } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, POWER_UNITS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { GridPlacesRanking } from "./GridPlacesRanking";

import type { PowerUnitsResponse } from "./powerUnitsModel";
import type { PowerUnitsSeeds } from "./usePowerUnits";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

async function renderRanking(data: unknown = POWER_UNITS_2026) {
  server.use(http.get(apiUrl("/api/race-control/power-units/2026"), () => HttpResponse.json(data as never)));
  const seeds = { powerUnits: Promise.resolve(data), teams: Promise.resolve(null) } as unknown as PowerUnitsSeeds;
  await act(() => {
    renderWithProviders(
      <Suspense fallback={null}>
        <GridPlacesRanking year={2026} seeds={seeds} />
      </Suspense>,
    );
    return Promise.resolve();
  });
}

/** A copy of the capture for a case to edit; the fixture itself is never touched. */
function copy(): PowerUnitsResponse {
  return structuredClone(POWER_UNITS_2026);
}

/** Only car 51 loses places, so its shared seat is the story. */
function onlySeat51(): PowerUnitsResponse {
  const data = copy();
  for (const car of data.cars) car.penalties.grid_places = car.car_number === 51 ? 5 : 0;
  return data;
}

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
});

describe("GridPlacesRanking", () => {
  it("ranks the 16 cars that lost places, the most first", async () => {
    await renderRanking();

    expect(screen.getByRole("heading", { name: "Car #5 has the most grid-place penalties" })).toBeInTheDocument();
    const items = within(screen.getByRole("list", { name: "Power-unit grid-place penalties by car" })).getAllByRole(
      "listitem",
    );
    expect(items).toHaveLength(16);
    expect(items[0]).toHaveTextContent("#5");
    expect(items[0]).toHaveTextContent("Bortoleto");
    expect(items[0]).toHaveTextContent("90");
  });

  it("tells the shared car's story", async () => {
    await renderRanking();

    expect(screen.getByText("Car 6")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "One car, two drivers" })).toBeInTheDocument();
    const story = screen.getByText("Car 6").closest("figure")!.querySelectorAll("p")[1];
    expect(story.textContent).toBe(
      "Hadjar raced it as #6 in every round so far except R12–R14, when Lawson (#30) stood in. Elements belong to the car, so the penalties follow the car, never the driver.",
    );
  });

  it("names every stand-in with the rounds he raced when there are several", async () => {
    await renderRanking(onlySeat51());

    expect(screen.getByRole("heading", { name: "One car, three drivers" })).toBeInTheDocument();
    expect(screen.getByText("Car 51").closest("figure")?.textContent).toMatch(
      /\(#\d+, R19\) and .*\(#\d+, R20\) stood in/,
    );
  });

  it("writes the count as a number past four drivers", async () => {
    const data = onlySeat51();
    const seat = data.cars.find((car) => car.car_number === 51)!;
    seat.drivers = [...seat.drivers, ...seat.drivers.map((stint, index) => ({ ...stint, id: `extra-${index}` }))];
    await renderRanking(data);

    expect(screen.getByRole("heading", { name: "One car, 6 drivers" })).toBeInTheDocument();
  });

  it("says so, with no bars and no card, when nobody lost places", async () => {
    const data = copy();
    for (const car of data.cars) {
      car.penalties.grid_places = 0;
      car.drivers = car.drivers.slice(0, 1);
    }
    await renderRanking(data);

    expect(screen.getByRole("heading", { name: "No power-unit grid-place penalty this season" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: /grid-place penalties by car/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/One car,/)).not.toBeInTheDocument();
  });

  it("states the source and nothing more when all is well", async () => {
    await renderRanking();

    expect(screen.getByText(/checked hourly · allocations as the FIA states them/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("lists a note, linked when it has a document", async () => {
    const data = copy();
    data.unread = [{ event: "Monaco", title: "Doc 9", url: "https://fia/9", reason: "scanned" }];
    data.warnings = ["Totals disagree"];
    await renderRanking(data);

    expect(screen.getByRole("link", { name: /Monaco: Doc 9 could not be read/ })).toHaveAttribute(
      "href",
      "https://fia/9",
    );
    expect(screen.getByText("Totals disagree")).toBeInTheDocument();
  });

  it("gives the reason when nothing is collected", async () => {
    await renderRanking({ ...POWER_UNITS_2026, available: false, reason: "Not collected yet.", cars: [] });

    expect(screen.getByText("Not collected yet.")).toBeInTheDocument();
  });
});
