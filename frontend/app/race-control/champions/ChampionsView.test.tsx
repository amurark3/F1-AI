import { act, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { CHAMPION_STATS } from "@/test/fixtures";
import { CHAMPIONS } from "@/test/fixtures/champions";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { ChampionsView } from "./ChampionsView";

import type { ChampionsSeeds } from "./useChampionsSections";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

function seeds(changes: Partial<ChampionsSeeds> = {}): ChampionsSeeds {
  return {
    latest: Promise.resolve(CHAMPIONS.latest),
    stats: Promise.resolve(CHAMPION_STATS),
    champions: Promise.resolve(CHAMPIONS.list),
    ...changes,
  };
}

async function renderView(changes: Partial<ChampionsSeeds> = {}) {
  await act(() => {
    renderWithProviders(<ChampionsView seeds={seeds(changes)} />);
    return Promise.resolve();
  });
}

describe("ChampionsView", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(
      http.get(apiUrl("/api/champions/latest"), () => HttpResponse.json(CHAMPIONS.latest)),
      http.get(apiUrl("/api/champions/stats"), () => HttpResponse.json(CHAMPION_STATS)),
      http.get(apiUrl("/api/champions"), () => HttpResponse.json(CHAMPIONS.list)),
    );
  });

  it("opens with the latest champion and his three records", async () => {
    await renderView();

    expect(await screen.findByRole("heading", { level: 1, name: "Antonelli joins the list" })).toBeInTheDocument();
    const records = screen.getByRole("list", { name: "Records" });
    expect(within(records).getAllByRole("listitem")).toHaveLength(3);
    expect(within(records).getByText("20 y 68 d")).toBeInTheDocument();
    expect(within(records).getByText("36th")).toBeInTheDocument();
  });

  it("ranks the titles on two leaderboards, ties kept whole", async () => {
    await renderView();

    const driversList = await screen.findByRole("list", { name: "Drivers' titles" });
    expect(within(driversList).getAllByRole("listitem")).toHaveLength(11);
    expect(within(screen.getByRole("list", { name: "Constructors' titles" })).getAllByRole("listitem")).toHaveLength(9);
    expect(screen.getByText("Hamilton and Schumacher, 7 each")).toBeInTheDocument();
    expect(screen.getByText("Ferrari lead with 16")).toBeInTheDocument();
  });

  it("lays every season out by decade, the latest champion in gold", async () => {
    await renderView();

    const link = await screen.findByRole("link", {
      name: "2026: Kimi Antonelli, constructors' champion Mercedes, clinched with 3 rounds still to run",
    });
    expect(screen.getAllByRole("heading", { level: 3, name: /^\d{4}s$/ })).toHaveLength(8);
    expect(screen.getAllByRole("link", { name: /^\d{4}: / })).toHaveLength(77);
    expect(link).toHaveAttribute("href", "/race-control/champions/2026");
    expect(link).toHaveClass("border-rc-gold");
    expect(link.querySelector("i")).not.toBeNull();

    const fangio = screen.getByRole("link", { name: "1957: Juan Manuel Fangio" });
    expect(fangio).not.toHaveClass("border-rc-gold");
    expect(fangio.querySelector("i")).toBeNull();
    expect(
      screen.getByText("Source: f1db · 2026 after round 20 of 23 · constructors' title awarded from 1958"),
    ).toBeInTheDocument();
  });

  // Derived: the captured list with 2026's drivers' title reopened.
  it("reads Open for a season whose title is undecided", async () => {
    const [first, ...rest] = CHAMPIONS.list.seasons ?? [];
    const open = {
      seasons: [{ ...first, driver_champion: { ...first.driver_champion!, title_decided: false } }, ...rest],
    };
    server.use(http.get(apiUrl("/api/champions"), () => HttpResponse.json(open)));
    await renderView({ champions: Promise.resolve(open) });

    expect(await screen.findByRole("link", { name: "2026: title still open" })).toHaveTextContent("Open");
  });

  it("draws an empty wall for a payload without seasons", async () => {
    server.use(http.get(apiUrl("/api/champions"), () => HttpResponse.json({})));
    await renderView({ champions: Promise.resolve({}) });

    expect(await screen.findByText("Source: f1db")).toBeInTheDocument();
    expect(screen.queryAllByRole("link", { name: /^\d{4}: / })).toHaveLength(0);
  });

  it("keeps the hero and the wall when the leaderboards fail", async () => {
    server.use(http.get(apiUrl("/api/champions/stats"), () => HttpResponse.json({}, { status: 500 })));
    await renderView({ stats: Promise.resolve(null) });

    expect(await screen.findByText("Request failed: 500 Internal Server Error")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Antonelli joins the list" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /^\d{4}: / })).toHaveLength(77);
  });

  it("shows no hero for an error payload and no bars for an empty leaderboard", async () => {
    const error = { ...CHAMPIONS.latest, error: "No decided drivers' title in f1db" };
    server.use(
      http.get(apiUrl("/api/champions/latest"), () => HttpResponse.json(error)),
      http.get(apiUrl("/api/champions/stats"), () => HttpResponse.json({})),
    );
    await renderView({ latest: Promise.resolve(error), stats: Promise.resolve({}) });

    expect(await screen.findAllByText("No titles recorded.")).toHaveLength(2);
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
  });
});
