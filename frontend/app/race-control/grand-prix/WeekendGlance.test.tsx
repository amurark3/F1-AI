import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, MEXICO_CITY_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { WeekendGlance } from "./WeekendGlance";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const GLANCE = MEXICO_CITY_2026.glance;

function answer(body: unknown, status = 200): void {
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
    http.get(apiUrl("/api/race-control/glance/2026/19"), () =>
      HttpResponse.json(body as Record<string, unknown>, { status }),
    ),
  );
}

describe("WeekendGlance", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  });

  it("shows last year's pole sitter, not its winner, and says no power-unit documents are collected", async () => {
    answer(GLANCE);
    renderWithProviders(<WeekendGlance year={2026} round={19} />);

    expect(screen.getByText("Reading this circuit's history…")).toBeInTheDocument();
    expect(await screen.findByText("2025 pole")).toBeInTheDocument();
    expect(screen.queryByText("2025 winner")).not.toBeInTheDocument();
    expect(screen.getByText("Lando Norris")).toBeInTheDocument();
    expect(screen.getByText(GLANCE.power_units.reason)).toBeInTheDocument();
  });

  it("says so when the circuit has no earlier race, and falls back to a generic reason", async () => {
    answer({ ...GLANCE, previous: null, power_units: { available: false, reason: null, decisions: [] } });
    renderWithProviders(<WeekendGlance year={2026} round={19} />);

    expect(await screen.findByText("No earlier race at this circuit.")).toBeInTheDocument();
    expect(screen.getByText("Last pole")).toBeInTheDocument();
    expect(screen.getByText("Power-unit decisions are not available.")).toBeInTheDocument();
  });

  it("lists the power-unit penalties decided this weekend, each linked to its FIA document", async () => {
    const decision = {
      title: "Decision - Power unit elements",
      url: "https://example.test/doc.pdf",
      published: "2026-10-30T10:00:00Z",
      number: 58,
      session: "Race",
      outcome: "grid_drop",
      places: 10,
      nominal_places: null,
      summary: "Exceeded the allowance",
      elements: [],
      car_number: 1,
      team: "Red Bull",
      team_id: "red-bull",
      driver: { id: "max-verstappen", name: "Max Verstappen", code: "VER", car_number: 1 },
    };
    answer({ ...GLANCE, power_units: { available: true, reason: null, decisions: [decision] } });
    renderWithProviders(<WeekendGlance year={2026} round={19} />);

    expect(await screen.findByText("−10 grid places")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /#1/ })).toHaveAttribute("href", "/race-control/power-units/1");
    expect(screen.getByLabelText("FIA document: Decision - Power unit elements")).toBeInTheDocument();
  });

  it("says when nobody was penalised, and when the history could not be loaded", async () => {
    answer({ ...GLANCE, power_units: { available: true, reason: null, decisions: [] } });
    const { unmount } = renderWithProviders(<WeekendGlance year={2026} round={19} />);
    expect(await screen.findByText("No power-unit penalty decided this weekend.")).toBeInTheDocument();
    unmount();

    answer({ detail: "boom" }, 500);
    renderWithProviders(<WeekendGlance year={2026} round={19} />);
    await waitFor(() => expect(screen.getByText("This round's history could not be loaded.")).toBeInTheDocument());
  });
});
