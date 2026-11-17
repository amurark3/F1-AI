import { act, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Suspense } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, OVERVIEW_SEGMENTS_2026, STANDINGS_PROGRESSION_2026, TEAMS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { StandingsHero } from "./StandingsHero";

import type { StandingsSeeds } from "./useStandingsSections";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

function seeds(changes: Partial<StandingsSeeds> = {}): StandingsSeeds {
  return {
    teams: Promise.resolve(TEAMS_2026),
    shell: Promise.resolve(OVERVIEW_SEGMENTS_2026.shell),
    progression: Promise.resolve(STANDINGS_PROGRESSION_2026),
    ...changes,
  } as StandingsSeeds;
}

/** Rendered inside an awaited `act`, so React can settle the `use()` of the seed promises. */
async function renderHero(changes: Partial<StandingsSeeds> = {}) {
  let rendered: ReturnType<typeof renderWithProviders> | undefined;
  await act(() => {
    rendered = renderWithProviders(
      <Suspense fallback={null}>
        <StandingsHero year={2026} seeds={seeds(changes)} />
      </Suspense>,
    );
    return Promise.resolve();
  });
  return rendered!;
}

function tile(label: string): HTMLElement {
  const eyebrow = screen.getByText(label, { selector: "p" });
  return eyebrow.parentElement!;
}

describe("StandingsHero", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("is the champion's hero once the title is won", async () => {
    await renderHero();

    expect(await screen.findByRole("heading", { level: 1, name: "Kimi Antonelli" })).toBeInTheDocument();
    expect(screen.getByText("2026 World Champion")).toBeInTheDocument();
    expect(screen.getByText("380")).toBeInTheDocument();
    expect(screen.getByText("Mercedes · 9 wins from 19 races")).toBeInTheDocument();
    expect(await screen.findByText("119 points clear of Verstappen after round 19.")).toBeInTheDocument();
    expect(within(tile("Fight for second")).getByText("16")).toBeInTheDocument();
    expect(within(tile("Constructors")).getByText("126")).toBeInTheDocument();
    expect(within(tile("Races left")).getByText("4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^after round 19 · confirmed/ })).toBeInTheDocument();
  });

  it("switches to the constructors by keyboard, where the title is still open", async () => {
    const { user } = await renderHero();
    await screen.findByRole("heading", { level: 1, name: "Kimi Antonelli" });

    screen.getByRole("radio", { name: "Drivers" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(await screen.findByRole("heading", { level: 1, name: "Mercedes" })).toBeInTheDocument();
    expect(screen.getByText("Constructors' leader")).toBeInTheDocument();
    expect(screen.getByText("126 points clear of Ferrari after round 19.")).toBeInTheDocument();
    expect(within(tile("Rivals in reach")).getByText("1")).toBeInTheDocument();
    expect(within(tile("Drivers")).getByText("Antonelli clinched · 100 left")).toBeInTheDocument();
  });

  it("claims no title, and shows no stakes tiles, when the shell is missing and no clinch is known", async () => {
    server.use(
      http.get(apiUrl("/api/race-control/overview/2026/shell"), () => new HttpResponse(null, { status: 500 })),
    );
    await renderHero({ shell: Promise.resolve(null), progression: Promise.resolve(null) });

    expect(await screen.findByText("Championship leader")).toBeInTheDocument();
    expect(screen.queryByText("2026 World Champion")).not.toBeInTheDocument();
    expect(screen.queryByText("Races left")).not.toBeInTheDocument();
    expect(screen.getByText("Constructors", { selector: "p" })).toBeInTheDocument();
  });

  it("says no round has paid points when the table has no leader pair", async () => {
    const empty = { ...TEAMS_2026, drivers: [], as_of_round: null };
    await renderHero({ teams: Promise.resolve(empty) });

    expect(await screen.findByRole("heading", { level: 1, name: "Standings" })).toBeInTheDocument();
    expect(screen.getByText("No round has paid points yet.")).toBeInTheDocument();
  });
});
