import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, POWER_UNITS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { SeatNames, UnavailableNote } from "./PowerUnitsParts";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const car = (number: number) => POWER_UNITS_2026.cars.find((item) => item.car_number === number)!;

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
});

describe("SeatNames", () => {
  it("lists a stand-in with his own number, never the car's", async () => {
    const { container } = renderWithProviders(<SeatNames car={car(6)} year={2026} />);

    await waitFor(() => expect(container).toHaveTextContent("Hadjar / Lawson#30"));
    expect(screen.queryByText("Shared seat")).not.toBeInTheDocument();
  });

  it("tags a shared seat only when asked", () => {
    renderWithProviders(<SeatNames car={car(6)} year={2026} tagShared />);

    expect(screen.getByText("Shared seat")).toBeInTheDocument();
  });

  it("tags nothing on a car with one driver", () => {
    const { container } = renderWithProviders(<SeatNames car={car(12)} year={2026} tagShared />);

    expect(container).not.toHaveTextContent("Shared seat");
    expect(container).not.toHaveTextContent("#");
  });
});

describe("UnavailableNote", () => {
  it("gives the payload's reason, or a default", () => {
    const { rerender } = renderWithProviders(<UnavailableNote data={{ ...POWER_UNITS_2026, reason: "Because." }} />);
    expect(screen.getByText("Because.")).toBeInTheDocument();

    rerender(<UnavailableNote data={{ ...POWER_UNITS_2026, reason: undefined }} />);
    expect(screen.getByText("Power-unit usage hasn't been collected for this season yet.")).toBeInTheDocument();
  });
});
