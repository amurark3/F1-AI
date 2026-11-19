import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import {
  ALLOCATION_ANTONELLI,
  ALLOCATION_HAMILTON,
  ALLOCATION_RESPONSE,
  ALLOCATION_RUSSELL,
} from "@/test/fixtures/powerUnitsAllocation";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { CarAllocations } from "./CarAllocations";

import type { PowerUnitsResponse } from "../power-units/powerUnitsModel";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const MERCEDES = { kind: "team", teamId: "mercedes" } as const;
const HAMILTON = { kind: "driver", driverId: "lewis-hamilton", lastName: "Hamilton" } as const;

function answer(body: unknown, status = 200): void {
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026 as never)),
    http.get(apiUrl("/api/race-control/power-units/:year"), () =>
      HttpResponse.json(body as Record<string, unknown>, { status }),
    ),
  );
}

function renderCard(scope: Parameters<typeof CarAllocations>[0]["scope"], body: unknown = ALLOCATION_RESPONSE) {
  answer(body);
  return renderWithProviders(<CarAllocations year={2026} scope={scope} />);
}

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
});

describe("CarAllocations on a team page", () => {
  it("shows the section head, the computed title and the sub", async () => {
    renderCard(MERCEDES);

    expect(
      await screen.findByRole("heading", {
        level: 3,
        name: "Both cars are past the allocation: 90 grid places imposed",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Power units" })).toBeInTheDocument();
    expect(screen.getByText("Elements used against the season's allocation")).toBeInTheDocument();
    expect(screen.getByText("Counted from the FIA's documents through round 19")).toBeInTheDocument();
  });

  it("lists the team's cars in a table with a column per element and its allowance", async () => {
    renderCard(MERCEDES);

    const table = await screen.findByRole("table", { name: /Both cars are past the allocation/ });
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers).toEqual(["Car", "ICE/4", "TC/4", "EXH/4", "MGU-K/3", "ES/3", "PU-CE/3", "PU-ANC/6", "Grid places"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    const first = within(rows[0]);
    expect(first.getByRole("rowheader")).toHaveTextContent("#12");
    expect(first.getByRole("link")).toHaveAttribute("href", "/race-control/power-units/12");
    // The surname comes from the season directory, which answers after the table paints.
    expect(await first.findByText("Antonelli")).toBeInTheDocument();
  });

  it("says each element in words on its pips, and prints the count", async () => {
    renderCard(MERCEDES);

    const rows = (await screen.findAllByRole("row")).slice(1);
    const first = within(rows[0]);
    expect(first.getAllByRole("img").map((pips) => pips.getAttribute("aria-label"))).toEqual([
      "5 of 4 used, 1 beyond the allocation",
      "3 of 4 used",
      "3 of 4 used",
      "2 of 3 used",
      "4 of 3 used, 1 beyond the allocation",
      "4 of 3 used, 1 beyond the allocation",
      "6 of 6 used",
    ]);
    const counts = first.getAllByText(/^\d$/, { selector: "[aria-hidden='true']" });
    expect(counts[0]).toHaveClass("text-rc-red-text");
    expect(counts[1]).toHaveClass("text-rc-ink-3");
  });

  it("draws used, empty and beyond pips", async () => {
    renderCard(MERCEDES);

    const pips = (await screen.findAllByRole("img"))[0];
    expect(pips.querySelectorAll("[data-pip='used']")).toHaveLength(4);
    expect(pips.querySelectorAll("[data-pip='beyond']")).toHaveLength(1);
    const unused = screen.getAllByRole("img")[1];
    expect(unused.querySelectorAll("[data-pip='empty']")).toHaveLength(1);
  });

  it("prints the grid places imposed, and a dash for none", async () => {
    renderCard({ kind: "team", teamId: "ferrari" });

    const row = (await screen.findAllByRole("row"))[1];
    expect(within(row).getByText("—")).toBeInTheDocument();
    expect(
      screen.getByText("No grid penalties · Counted from the FIA's documents through round 19"),
    ).toBeInTheDocument();
  });

  it("adds pit-lane and back-of-grid starts to the places", async () => {
    const body: PowerUnitsResponse = {
      ...ALLOCATION_RESPONSE,
      cars: [
        {
          ...ALLOCATION_HAMILTON,
          penalties: { ...ALLOCATION_HAMILTON.penalties, grid_places: 10, pit_lane_starts: 1, back_of_grid: 2 },
        },
      ],
    };
    renderCard({ kind: "team", teamId: "ferrari" }, body);

    expect(await screen.findByText("10")).toBeInTheDocument();
    expect(screen.getByText("+ 1 pit lane")).toBeInTheDocument();
    expect(screen.getByText("+ 2 back of grid")).toBeInTheDocument();
  });

  it("links to every car and every FIA document, and keys the pips", async () => {
    renderCard(MERCEDES);

    expect(await screen.findByRole("link", { name: "All 3 cars and every FIA document →" })).toHaveAttribute(
      "href",
      "/race-control/power-units",
    );
    const legend = screen.getByRole("list", { name: "Legend" });
    expect(
      within(legend)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["Used", "Unused", "Beyond the allocation"]);
  });

  it("scrolls the table sideways inside its own box", async () => {
    renderCard(MERCEDES);

    const table = await screen.findByRole("table");
    expect(table.parentElement).toHaveClass("overflow-x-auto");
    expect(table).toHaveClass("min-w-[780px]");
  });

  it("lists both surnames of a car that two drivers shared", async () => {
    const shared = {
      ...ALLOCATION_ANTONELLI,
      drivers: [...ALLOCATION_ANTONELLI.drivers, ...ALLOCATION_RUSSELL.drivers],
    };
    renderCard(MERCEDES, { ...ALLOCATION_RESPONSE, cars: [shared] });

    await waitFor(() => expect(screen.getByRole("rowheader")).toHaveTextContent("#12Antonelli / Russell"));
  });

  it("prints a count with no allocation as plain pips", async () => {
    const open = {
      ...ALLOCATION_RESPONSE,
      elements: ALLOCATION_RESPONSE.elements?.map((element) => ({ ...element, allowance: null })),
      cars: [
        {
          ...ALLOCATION_HAMILTON,
          elements: ALLOCATION_HAMILTON.elements.map((element) => ({ ...element, allowance: null })),
        },
      ],
    };
    renderCard({ kind: "team", teamId: "ferrari" }, open);

    expect((await screen.findAllByRole("img"))[0]).toHaveAttribute("aria-label", "4 used");
    expect(screen.getByRole("columnheader", { name: "ICE" })).toBeInTheDocument();
  });

  it("leaves the through-round out when the payload names none, and tolerates no element list", async () => {
    renderCard(MERCEDES, { ...ALLOCATION_RESPONSE, as_of: null, elements: undefined });

    expect(await screen.findByText("Counted from the FIA's documents")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader")).toHaveLength(2);
  });

  it("leaves a cell empty for an element a car has no record of", async () => {
    const extra = { code: "XX", name: "Extra", allowance: 2, allowance_source: null };
    renderCard(MERCEDES, { ...ALLOCATION_RESPONSE, elements: [...(ALLOCATION_RESPONSE.elements ?? []), extra] });

    const row = (await screen.findAllByRole("row"))[1];
    expect(within(row).getAllByRole("img")).toHaveLength(7);
    expect(screen.getByRole("columnheader", { name: "XX/2" })).toBeInTheDocument();
  });
});

describe("CarAllocations on a driver page", () => {
  it("heads the section 02 Power unit and names the car by team and rounds raced", async () => {
    renderCard(HAMILTON);

    expect(await screen.findByRole("heading", { level: 2, name: "Power unit" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: "Car #44 has used its full allocation of every element" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("rowheader")).toHaveTextContent("#44Ferrari");
    expect(screen.getByText("R1–R10")).toBeInTheDocument();
  });

  it("links the one car in full", async () => {
    renderCard(HAMILTON);

    expect(await screen.findByRole("link", { name: "Car #44 in full: every part and FIA document →" })).toHaveAttribute(
      "href",
      "/race-control/power-units/44",
    );
  });
});

describe("CarAllocations in its other states", () => {
  it("holds a skeleton while pending, and the page around it needs nothing", async () => {
    answer(ALLOCATION_RESPONSE);
    renderWithProviders(<CarAllocations year={2026} scope={MERCEDES} />);

    expect(document.querySelector("[aria-busy='true']")).toBeInTheDocument();
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("says Power units unavailable with a Retry when the endpoint fails, and recovers", async () => {
    answer({ detail: "boom" }, 500);
    const { user } = renderWithProviders(<CarAllocations year={2026} scope={MERCEDES} />);

    expect(await screen.findByText("Power units unavailable")).toBeInTheDocument();
    answer(ALLOCATION_RESPONSE);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("explains a season with no power-unit data, with and without the reason", async () => {
    renderCard(MERCEDES, {
      year: 2026,
      available: false,
      reason: "No FIA documents for 2026 yet.",
      cars: [],
      unread: [],
      warnings: [],
    });
    expect(
      await screen.findByText("Power-unit usage isn't available: No FIA documents for 2026 yet."),
    ).toBeInTheDocument();
  });

  it("explains an unavailable season that gave no reason", async () => {
    renderCard(MERCEDES, { year: 2026, available: false, cars: [], unread: [], warnings: [] });
    expect(await screen.findByText("Power-unit usage isn't available.")).toBeInTheDocument();
  });

  it("says plainly when no car matches the team or the driver", async () => {
    renderCard({ kind: "team", teamId: "cadillac" });
    expect(await screen.findByText("No power-unit records for this team this season.")).toBeInTheDocument();
  });

  it("says plainly when no car matches the driver", async () => {
    renderCard({ kind: "driver", driverId: "nobody", lastName: "Nobody" });
    expect(await screen.findByText("No power-unit records for this driver this season.")).toBeInTheDocument();
  });
});
