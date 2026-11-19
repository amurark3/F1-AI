import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { POWER_UNITS_2026 } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { renderCar } from "@/test/renderCar";

import { CarHero, CarHeroFallback } from "./CarHero";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
});

function tile(label: string): HTMLElement {
  return screen.getByText(label, { selector: "p" }).parentElement!;
}

describe("CarHero for car 6", () => {
  it("shows the eyebrow, the h1, the engine figure and the lineup", async () => {
    await renderCar(CarHero, POWER_UNITS_2026);

    expect(
      screen.getByText("Power units · 2026 · after round 20 · latest FIA document: São Paulo GP doc 57"),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Car 6");
    expect(screen.getByText(/Every power-unit element fitted to car 6/)).toBeInTheDocument();
    expect(screen.getByText("fitted against an allocation of 4, the most of any car this season.")).toBeInTheDocument();
    expect(screen.getByText("engines")).toBeInTheDocument();
    const seats = screen.getAllByRole("heading", { level: 2 });
    expect(seats).toHaveLength(2);
    expect(seats[0]).toHaveTextContent("Isack Hadjar");
    expect(seats[1]).toHaveTextContent("Liam Lawson");
    expect(within(seats[1]).getByText("Stand-in")).toBeInTheDocument();
    expect(screen.getByText("17 rounds")).toBeInTheDocument();
    expect(screen.getByText("R12–R14")).toBeInTheDocument();
    expect(screen.getByText("−35 grid places, 2 pit-lane starts")).toBeInTheDocument();
  });

  it("shows the four totals, the first as the lead", async () => {
    await renderCar(CarHero, POWER_UNITS_2026);

    expect(tile("Grid places imposed")).toHaveTextContent("70R10 −30 · R13 −35 · R16 −5");
    expect(tile("Pit-lane starts")).toHaveTextContent(
      "2ordered by power-unit rulings · R4 Miami GP · R17 Singapore GP",
    );
    expect(tile("Elements over")).toHaveTextContent("7of 7every element past its allocation");
    expect(tile("Extra units")).toHaveTextContent("15beyond the allocation · ICE 4");
    expect(tile("Grid places imposed")).toHaveAttribute("data-lead");
  });
});

describe("CarHero states", () => {
  it("lets the data win over the URL: car 22 is car 30", async () => {
    await renderCar(CarHero, POWER_UNITS_2026, { segment: "22" });

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Car 30");
  });

  it("omits the engine figure for a car with no engine row", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    const target = changed.cars.find((c) => c.car_number === 12)!;
    target.elements = target.elements.filter((e) => e.code !== "ICE");
    await renderCar(CarHero, changed, { segment: "12" });

    expect(screen.queryByText("engines")).not.toBeInTheDocument();
  });

  it("says no car runs under an unknown number, and keeps the h1", async () => {
    await renderCar(CarHero, POWER_UNITS_2026, { segment: "99" });

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Car 99");
    expect(screen.getByText("No 2026 car runs as #99.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See every car" })).toHaveAttribute("href", "/race-control/power-units");
  });

  it("gives the reason when the season is not collected", async () => {
    await renderCar(CarHero, { ...POWER_UNITS_2026, available: false, reason: "Not collected yet.", cars: [] });

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Car 6");
    expect(screen.getByText("Not collected yet.")).toBeInTheDocument();
    expect(screen.queryByText("Grid places imposed")).not.toBeInTheDocument();
  });

  it("shows the failure card under the h1 for an error payload", async () => {
    await renderCar(CarHero, { error: "boom" });

    expect(await screen.findByText("Car totals unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Car 6");
  });

  it("still shows the tiles for a car with no events", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    changed.cars.find((c) => c.car_number === 12)!.events = [];
    await renderCar(CarHero, changed, { segment: "12" });

    expect(screen.getByText("Grid places imposed")).toBeInTheDocument();
  });
});

describe("CarHeroFallback", () => {
  it("holds the h1 and a skeleton", () => {
    renderWithProviders(<CarHeroFallback year={2026} segment="6" />);

    expect(screen.getByRole("heading", { level: 1, name: "Car 6" })).toBeInTheDocument();
    expect(screen.getByText("Power units · 2026")).toBeInTheDocument();
  });
});
