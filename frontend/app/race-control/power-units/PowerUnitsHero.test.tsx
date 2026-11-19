import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Suspense } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, POWER_UNITS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { HeroFallback, PowerUnitsHero } from "./PowerUnitsHero";

import type { PowerUnitsResponse } from "./powerUnitsModel";
import type { PowerUnitsSeeds } from "./usePowerUnits";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const URL = apiUrl("/api/race-control/power-units/2026");

async function renderHero(seed: unknown, live: unknown = seed) {
  server.use(http.get(URL, () => HttpResponse.json(live as never)));
  const seeds = { powerUnits: Promise.resolve(seed), teams: Promise.resolve(null) } as unknown as PowerUnitsSeeds;
  await act(() => {
    renderWithProviders(
      <Suspense fallback={null}>
        <PowerUnitsHero year={2026} seeds={seeds} />
      </Suspense>,
    );
    return Promise.resolve();
  });
}

function tile(label: string): HTMLElement {
  return screen.getByText(label, { selector: "p" }).parentElement!;
}

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
});

describe("PowerUnitsHero", () => {
  it("shows the computed title, the eyebrow and the four tiles", async () => {
    await renderHero(POWER_UNITS_2026);

    expect(screen.getByRole("heading", { level: 1, name: "Engines over the limit" })).toBeInTheDocument();
    expect(
      screen.getByText("Power units · 2026 · after round 20 · latest FIA document: São Paulo GP doc 57"),
    ).toBeInTheDocument();
    expect(tile("Grid places imposed")).toHaveTextContent("685");
    expect(tile("Over on engines")).toHaveTextContent("15of 22");
    expect(tile("Pit-lane starts")).toHaveTextContent("7");
    expect(tile("Latest")).toHaveTextContent("−10");
    expect(tile("Latest")).toHaveTextContent("Bortoleto, São Paulo GP · ES, PU-CE (FIA doc 57)");
  });

  it("says so when no penalty has been imposed", async () => {
    const quiet: PowerUnitsResponse = structuredClone(POWER_UNITS_2026);
    for (const car of quiet.cars) for (const event of car.events) event.decisions = [];
    await renderHero(quiet);

    expect(tile("Latest")).toHaveTextContent("—No power-unit penalty this season");
  });

  it("keeps the page's h1 and gives the reason when nothing is collected", async () => {
    await renderHero({ ...POWER_UNITS_2026, available: false, reason: "Not collected yet.", cars: [] });

    expect(screen.getByRole("heading", { level: 1, name: "Power units" })).toBeInTheDocument();
    expect(screen.getByText("Not collected yet.")).toBeInTheDocument();
    expect(screen.queryByText("Grid places imposed")).not.toBeInTheDocument();
  });

  it("shows the failure card, still under its h1, for an error payload", async () => {
    await renderHero({ error: "boom" });

    expect(await screen.findByText("Power-unit totals unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Power units" })).toBeInTheDocument();
  });
});

describe("HeroFallback", () => {
  it("holds the h1 and a skeleton", () => {
    renderWithProviders(<HeroFallback year={2026} />);

    expect(screen.getByRole("heading", { level: 1, name: "Power units" })).toBeInTheDocument();
    expect(screen.getByText("Power units · 2026")).toBeInTheDocument();
  });
});
