import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { DIRECTORY_2026, TEAMS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { TeamsView } from "./TeamsView";

const TEAMS_URL = apiUrl("/api/race-control/teams/2026");
// Entity links read the directory for the calendar year, so match any season.
const DIRECTORY_URL = apiUrl("/api/profiles/:year/directory");

function serveDirectory(): void {
  server.use(http.get(DIRECTORY_URL, () => HttpResponse.json(DIRECTORY_2026)));
}

describe("TeamsView", () => {
  it("fetches the standings when the server render had none", async () => {
    serveDirectory();
    server.use(http.get(TEAMS_URL, () => HttpResponse.json(TEAMS_2026)));

    renderWithProviders(<TeamsView year={2026} initialTeams={null} />);

    expect(screen.getByText("Preparing championship hub")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Championship Standings" })).toBeInTheDocument();
    expect(screen.getByText("Mercedes · 380 pts")).toBeInTheDocument();
    expect(screen.getByText(/after round 19 · confirmed/)).toBeInTheDocument();
    const [mercedes] = await screen.findAllByRole("link", { name: "Mercedes" });
    expect(mercedes).toHaveAttribute("href", "/race-control/constructors/mercedes");
  });

  it("reports a failed request and recovers on retry", async () => {
    serveDirectory();
    server.use(
      // Handlers match in the order given: this one answers the first request
      // only, and the retry falls through to the payload below.
      http.get(TEAMS_URL, () => new HttpResponse(null, { status: 500 }), { once: true }),
      http.get(TEAMS_URL, () => HttpResponse.json(TEAMS_2026)),
    );

    const { user } = renderWithProviders(<TeamsView year={2026} initialTeams={null} />);

    expect(await screen.findByText("The standings API did not respond.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Mercedes · 380 pts")).toBeInTheDocument();
    expect(screen.queryByText("The standings API did not respond.")).not.toBeInTheDocument();
  });
});
