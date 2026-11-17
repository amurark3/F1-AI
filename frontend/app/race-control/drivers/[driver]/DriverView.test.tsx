import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, PROFILE_PAGES_2026 } from "@/test/fixtures";
import { ALLOCATION_RESPONSE } from "@/test/fixtures/powerUnitsAllocation";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { DriverView } from "./DriverView";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const { hamilton } = PROFILE_PAGES_2026;
const DRIVER_URL = apiUrl("/api/profiles/:year/drivers/:driver");

function answer(body: unknown, status = 200): void {
  server.use(http.get(DRIVER_URL, () => HttpResponse.json(body as Record<string, unknown>, { status })));
}

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026 as never)),
    http.get(apiUrl("/api/race-control/power-units/:year"), () => HttpResponse.json(ALLOCATION_RESPONSE as never)),
  );
});

describe("DriverView", () => {
  it("paints a seeded driver at once, with the power unit arriving on its own", async () => {
    renderWithProviders(<DriverView year={2026} driverId="lewis-hamilton" seed={hamilton} />);

    expect(screen.getByRole("heading", { level: 1, name: "Lewis Hamilton" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "The season, race by race" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: "Hamilton gained 13 places over the season" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Scored in 19 of 20 races" })).toBeInTheDocument();
    expect(document.querySelector(".h-\\[760px\\]")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: "Power unit" })).toBeInTheDocument();
  });

  it("shows a skeleton while unseeded, then the driver", async () => {
    answer(hamilton);
    renderWithProviders(<DriverView year={2026} driverId="lewis-hamilton" seed={null} />);

    expect(document.querySelector("[aria-busy='true']")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: "Lewis Hamilton" })).toBeInTheDocument();
  });

  it("says the id is not a driver of the season", async () => {
    renderWithProviders(
      <DriverView year={2026} driverId="nobody" seed={{ year: 2026, status: "not_found", driver: null } as never} />,
    );

    expect(await screen.findByText("No 2026 driver with the id “nobody”.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All teams" })).toHaveAttribute("href", "/race-control/constructors");
  });

  it("says Driver season unavailable with a Retry, and recovers", async () => {
    answer({ detail: "boom" }, 500);
    const { user } = renderWithProviders(<DriverView year={2026} driverId="lewis-hamilton" seed={null} />);

    expect(await screen.findByText("Driver season unavailable")).toBeInTheDocument();
    answer(hamilton);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Lewis Hamilton" })).toBeInTheDocument();
  });

  it("keeps the driver and marks it stale when a refresh fails", async () => {
    answer({ detail: "boom" }, 500);
    renderWithProviders(<DriverView year={2026} driverId="lewis-hamilton" seed={hamilton} />);

    expect(await screen.findByText("Couldn't refresh")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Lewis Hamilton" })).toBeInTheDocument();
  });

  it("keeps the driver standing when the power-unit endpoint fails", async () => {
    answer(hamilton);
    server.use(
      http.get(apiUrl("/api/race-control/power-units/:year"), () =>
        HttpResponse.json({ detail: "x" }, { status: 500 }),
      ),
    );
    renderWithProviders(<DriverView year={2026} driverId="lewis-hamilton" seed={hamilton} />);

    expect(await screen.findByText("Power units unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Lewis Hamilton" })).toBeInTheDocument();
  });
});
