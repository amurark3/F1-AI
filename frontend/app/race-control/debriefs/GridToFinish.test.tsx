import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { GridToFinish } from "./GridToFinish";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const R19 = DEBRIEF_R19.summary;

describe("GridToFinish", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("names the biggest climber and draws every car that started", async () => {
    renderWithProviders(<GridToFinish summary={R19} />);

    expect(await screen.findByRole("heading", { name: "Lawson came from the pit lane to P7" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Grid against finish" });
    expect(within(table).getAllByRole("row")).toHaveLength(23);
    expect(within(table).getByRole("row", { name: /Liam Lawson/ })).toHaveTextContent("PL");
    expect(within(table).getByRole("row", { name: /Lindblad/ })).toHaveTextContent("DNF L58");
  });

  it("says nobody gained when nobody did", () => {
    renderWithProviders(<GridToFinish summary={{ ...R19, classification: [{ ...R19.classification[0], grid: 1 }] }} />);

    expect(screen.getByRole("heading", { name: "Nobody gained places from the grid" })).toBeInTheDocument();
  });

  it("says places gained are not counted until the official grid is out", () => {
    renderWithProviders(<GridToFinish summary={{ ...R19, grid: { available: false, fia_document: null } }} />);

    expect(
      screen.getByText("The official starting grid isn't published yet, so places gained aren't counted."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
