import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, PROFILE_PAGES_2026 } from "@/test/fixtures";
import { ALLOCATION_RESPONSE } from "@/test/fixtures/powerUnitsAllocation";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { TeamView } from "./TeamView";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const { mercedes } = PROFILE_PAGES_2026;
const TEAM_URL = apiUrl("/api/profiles/:year/teams/:team");

function answer(body: unknown, status = 200): void {
  server.use(http.get(TEAM_URL, () => HttpResponse.json(body as Record<string, unknown>, { status })));
}

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026 as never)),
    http.get(apiUrl("/api/race-control/power-units/:year"), () => HttpResponse.json(ALLOCATION_RESPONSE as never)),
  );
});

describe("TeamView", () => {
  it("paints a seeded team at once: hero, figures, heat grid, weekends, and the power units after", async () => {
    renderWithProviders(<TeamView year={2026} teamId="mercedes" seed={mercedes} />);

    expect(screen.getByRole("heading", { level: 1, name: "Mercedes" })).toBeInTheDocument();
    expect(screen.getByText("Retirements")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Every finish" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Points by weekend" })).toBeInTheDocument();
    expect(document.querySelector(".h-\\[720px\\]")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: "Power units" })).toBeInTheDocument();
    expect(screen.getByText("Race result by round · through R20")).toBeInTheDocument();
  });

  it("leaves the aside off the heat grid's head when no results are published", async () => {
    renderWithProviders(<TeamView year={2026} teamId="mercedes" seed={{ ...mercedes, results_through: null }} />);

    expect(await screen.findByText("Race result by round")).toBeInTheDocument();
  });

  it("shows a skeleton while unseeded, then the team", async () => {
    answer(mercedes);
    renderWithProviders(<TeamView year={2026} teamId="mercedes" seed={null} />);

    expect(document.querySelector("[aria-busy='true']")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: "Mercedes" })).toBeInTheDocument();
  });

  it("says the id is not a team of the season", async () => {
    renderWithProviders(
      <TeamView year={2026} teamId="lotus" seed={{ year: 2026, status: "not_found", team: null } as never} />,
    );

    expect(await screen.findByText("No 2026 team with the id “lotus”.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All teams" })).toHaveAttribute("href", "/race-control/constructors");
  });

  it("says Team season unavailable with a Retry, and recovers", async () => {
    answer({ detail: "boom" }, 500);
    const { user } = renderWithProviders(<TeamView year={2026} teamId="mercedes" seed={null} />);

    expect(await screen.findByText("Team season unavailable")).toBeInTheDocument();
    answer(mercedes);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Mercedes" })).toBeInTheDocument();
  });

  it("keeps the team and marks it stale when a refresh fails", async () => {
    answer({ detail: "boom" }, 500);
    renderWithProviders(<TeamView year={2026} teamId="mercedes" seed={mercedes} />);

    expect(await screen.findByText("Couldn't refresh")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Mercedes" })).toBeInTheDocument();
  });

  it("keeps the team standing when the power-unit endpoint fails", async () => {
    server.use(
      http.get(apiUrl("/api/race-control/power-units/:year"), () =>
        HttpResponse.json({ detail: "x" }, { status: 500 }),
      ),
    );
    renderWithProviders(<TeamView year={2026} teamId="mercedes" seed={mercedes} />);

    expect(await screen.findByText("Power units unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Mercedes" })).toBeInTheDocument();
  });
});
