import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { PROFILE_PAGES_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { TeamsIndexView } from "./TeamsIndexView";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const INDEX = PROFILE_PAGES_2026.teams_index;
const TEAMS_URL = apiUrl("/api/profiles/:year/teams");

function answer(body: unknown, status = 200): void {
  server.use(http.get(TEAMS_URL, () => HttpResponse.json(body as Record<string, unknown>, { status })));
}

describe("TeamsIndexView", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  });

  it("paints a seeded index at once, with the computed title and eyebrow", () => {
    renderWithProviders(<TeamsIndexView year={2026} seed={INDEX} />);

    expect(screen.getByRole("heading", { level: 1, name: "Eleven teams" })).toBeInTheDocument();
    expect(screen.getByText("2026 constructors · after round 20")).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(11);
    expect(screen.getByText("652 pts · Leader")).toBeInTheDocument();
    expect(screen.getByText("510 pts · −142")).toBeInTheDocument();
    expect(document.querySelector("[aria-busy='true']")).not.toBeInTheDocument();
  });

  it("shows a skeleton under a plain title while unseeded, then the teams", async () => {
    answer(INDEX);
    renderWithProviders(<TeamsIndexView year={2026} seed={null} />);

    expect(screen.getByRole("heading", { level: 1, name: "Teams" })).toBeInTheDocument();
    expect(document.querySelector("[aria-busy='true']")).toBeInTheDocument();
    expect(screen.getByText("2026 constructors")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: "Eleven teams" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Mercedes/ })).toBeInTheDocument();
  });

  it("says Teams unavailable with a Retry when the backend fails, and recovers on retry", async () => {
    answer({ detail: "boom" }, 500);
    const { user } = renderWithProviders(<TeamsIndexView year={2026} seed={null} />);

    expect(await screen.findByText("Teams unavailable")).toBeInTheDocument();

    answer(INDEX);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Eleven teams" })).toBeInTheDocument();
  });

  it("keeps the cards and marks them stale when a refresh fails", async () => {
    answer({ detail: "boom" }, 500);
    renderWithProviders(<TeamsIndexView year={2026} seed={INDEX} />);

    expect(await screen.findByText("Couldn't refresh")).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(11);
  });

  it("lists the teams without round labels when no results are published yet", () => {
    renderWithProviders(<TeamsIndexView year={2026} seed={{ ...INDEX, results_through: null }} />);

    expect(screen.getAllByRole("link")).toHaveLength(11);
    expect(screen.queryByText("R12–14")).not.toBeInTheDocument();
  });

  it("says no teams are published when the list is empty", async () => {
    renderWithProviders(<TeamsIndexView year={2027} seed={{ ...INDEX, year: 2027, as_of_round: null, teams: [] }} />);

    await waitFor(() => expect(screen.getByText("No 2027 teams published yet.")).toBeInTheDocument());
    expect(screen.getByRole("heading", { level: 1, name: "Zero teams" })).toBeInTheDocument();
    expect(screen.getByText("2027 constructors")).toBeInTheDocument();
  });
});
