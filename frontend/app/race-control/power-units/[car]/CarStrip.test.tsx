import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { POWER_UNITS_2026 } from "@/test/fixtures";
import { renderCar } from "@/test/renderCar";

import { CarStrip } from "./CarStrip";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
});

describe("CarStrip", () => {
  it("links every car by number and marks the current one", async () => {
    await renderCar(CarStrip, POWER_UNITS_2026);

    const nav = screen.getByRole("navigation", { name: "Other cars" });
    const links = nav.querySelectorAll("a");
    expect(links).toHaveLength(POWER_UNITS_2026.cars.length);
    expect(links[0]).toHaveAttribute("href", "/race-control/power-units/1");
    const current = screen.getByRole("link", { current: "page" });
    expect(current).toHaveAttribute("aria-label", "Car 6 · Isack Hadjar · Red Bull");
    expect(current).toHaveAttribute("title", "Isack Hadjar · Red Bull");
  });

  it("marks the car a stand-in's number leads to", async () => {
    await renderCar(CarStrip, POWER_UNITS_2026, { segment: "22" });

    expect(screen.getByRole("link", { current: "page" })).toHaveTextContent("30");
  });

  it("draws nothing when the season is not collected", async () => {
    await renderCar(CarStrip, { ...POWER_UNITS_2026, available: false, cars: [] });

    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("says so when the payload is an error", async () => {
    await renderCar(CarStrip, { error: "boom" });

    expect(await screen.findByText("Cars unavailable")).toBeInTheDocument();
  });
});
