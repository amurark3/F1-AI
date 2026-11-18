import { act, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import {
  CLINCH_2026,
  DIRECTORY_2026,
  OVERVIEW_SEGMENTS_2026,
  STANDINGS_PROGRESSION_2026,
  TEAMS_2026,
} from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { StandingsView } from "./StandingsView";

import type { StandingsSeeds } from "./useStandingsSections";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const TEAMS_URL = apiUrl("/api/race-control/teams/2026");
const SHELL_URL = apiUrl("/api/race-control/overview/2026/shell");
const PROGRESSION_URL = apiUrl("/api/race-control/standings/2026/progression");

function seeds(changes: Partial<StandingsSeeds> = {}): StandingsSeeds {
  return {
    teams: Promise.resolve(TEAMS_2026),
    shell: Promise.resolve(OVERVIEW_SEGMENTS_2026.shell),
    progression: Promise.resolve(STANDINGS_PROGRESSION_2026),
    ...changes,
  } as StandingsSeeds;
}

async function renderView(changes: Partial<StandingsSeeds> = {}) {
  let rendered: ReturnType<typeof renderWithProviders> | undefined;
  await act(() => {
    rendered = renderWithProviders(<StandingsView year={2026} seeds={seeds(changes)} />);
    return Promise.resolve();
  });
  return rendered!;
}

describe("StandingsView", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(TEAMS_URL, () => HttpResponse.json(TEAMS_2026)),
      http.get(SHELL_URL, () => HttpResponse.json(OVERVIEW_SEGMENTS_2026.shell)),
      http.get(PROGRESSION_URL, () => HttpResponse.json(STANDINGS_PROGRESSION_2026)),
      http.get(apiUrl("/api/race-control/standings/:year/clinch"), () =>
        HttpResponse.json(CLINCH_2026.afterRound19 as never),
      ),
    );
  });

  it("renders every section from the seeds", async () => {
    await renderView();

    expect(screen.getByRole("heading", { name: "Drivers' order" })).toBeInTheDocument();
    const order = screen.getByRole("list", { name: "Drivers' championship points" });
    const rows = within(order).getAllByRole("listitem");
    expect(rows).toHaveLength(24);
    expect(rows[0]).toHaveTextContent("Champion");
    expect(rows[1]).toHaveTextContent("−119");

    const left = screen.getByRole("list", { name: "Constructors' championship points, places 1–6" });
    const right = screen.getByRole("list", { name: "Constructors' championship points, places 7–11" });
    expect(within(left).getAllByRole("listitem")).toHaveLength(6);
    expect(within(right).getAllByRole("listitem")).toHaveLength(5);

    expect(
      await screen.findByRole("heading", { name: "Antonelli led from Suzuka and never gave it back" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Kimi Antonelli" })).toBeInTheDocument();
    expect(await screen.findByText("Mercedes can clinch in São Paulo")).toBeInTheDocument();
  });

  it("links the names to their pages once the directory is in", async () => {
    await renderView();

    const [mercedes] = await screen.findAllByRole("link", { name: "Mercedes" });
    expect(mercedes).toHaveAttribute("href", "/race-control/constructors/mercedes");
  });

  it("keeps the other sections when the title race is unavailable, and recovers on retry", async () => {
    server.use(
      http.get(PROGRESSION_URL, () => new HttpResponse(null, { status: 500 }), { once: true }),
      http.get(PROGRESSION_URL, () => HttpResponse.json(STANDINGS_PROGRESSION_2026)),
    );
    const { user } = await renderView({ progression: Promise.resolve(null) });

    expect(await screen.findByText("Title race unavailable")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Drivers' championship points" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: /^Antonelli led from Suzuka/ })).toBeInTheDocument();
  });

  it("keeps the standings on screen, marked stale, when the refresh fails", async () => {
    server.use(http.get(TEAMS_URL, () => new HttpResponse(null, { status: 500 })));
    await renderView();

    expect((await screen.findAllByText("Couldn't refresh")).length).toBeGreaterThan(0);
    expect(screen.getByRole("list", { name: "Drivers' championship points" })).toBeInTheDocument();
    expect(screen.queryByText("Drivers' standings unavailable")).not.toBeInTheDocument();
  });

  it("says so in each section when the standings cannot be had", async () => {
    server.use(http.get(TEAMS_URL, () => new HttpResponse(null, { status: 500 })));
    await renderView({ teams: Promise.resolve(null) });

    expect(await screen.findByText("Drivers' standings unavailable")).toBeInTheDocument();
    expect(screen.getByText("Constructors' standings unavailable")).toBeInTheDocument();
    expect(screen.getByText("Standings unavailable")).toBeInTheDocument();
  });
});
