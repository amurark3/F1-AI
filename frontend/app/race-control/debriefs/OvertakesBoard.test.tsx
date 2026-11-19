import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { OvertakesBoard } from "./OvertakesBoard";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

describe("OvertakesBoard", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("ranks the six cars that made the most position changes", async () => {
    renderWithProviders(<OvertakesBoard overtakes={DEBRIEF_R19.overtakes} />);

    expect(await screen.findByRole("heading", { name: "Hadjar made the most position changes" })).toBeInTheDocument();
    expect(screen.getByText("On-track position changes made, OpenF1")).toBeInTheDocument();
    const rows = within(screen.getByRole("list", { name: "Position changes made" })).getAllByRole("listitem");
    expect(rows).toHaveLength(6);
    expect(rows[0]).toHaveTextContent("Isack Hadjar");
    expect(rows[0]).toHaveTextContent("28");
  });

  it("says OpenF1 has none when it has none", () => {
    renderWithProviders(<OvertakesBoard overtakes={{ available: false, total: 0, drivers: [] }} />);

    expect(screen.getByText("OpenF1 has no position changes for this race.")).toBeInTheDocument();
  });
});
