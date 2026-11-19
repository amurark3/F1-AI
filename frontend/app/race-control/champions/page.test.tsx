import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { CHAMPION_STATS } from "@/test/fixtures";
import { CHAMPIONS } from "@/test/fixtures/champions";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import ChampionsPage, { metadata } from "./page";

const champions = vi.hoisted(() => ({ getLatestChampion: vi.fn(), getChampionStats: vi.fn(), getChampions: vi.fn() }));

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/lib/server/champions", async (importActual) => ({
  ...(await importActual<Record<string, unknown>>()),
  ...champions,
}));

describe("the Champions page", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    champions.getLatestChampion.mockResolvedValue(CHAMPIONS.latest);
    champions.getChampionStats.mockResolvedValue(CHAMPION_STATS);
    champions.getChampions.mockResolvedValue(CHAMPIONS.list);
    server.use(
      http.get(apiUrl("/api/champions/latest"), () => HttpResponse.json(CHAMPIONS.latest)),
      http.get(apiUrl("/api/champions/stats"), () => HttpResponse.json(CHAMPION_STATS)),
      http.get(apiUrl("/api/champions"), () => HttpResponse.json(CHAMPIONS.list)),
    );
  });

  it("awaits nothing and hands the sections their seeds", async () => {
    let page: ReturnType<typeof ChampionsPage> | Promise<unknown> | undefined;
    await act(() => {
      page = ChampionsPage();
      renderWithProviders(page);
      return Promise.resolve();
    });

    expect(page).not.toBeInstanceOf(Promise);
    expect(champions.getLatestChampion).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("heading", { level: 1, name: "Antonelli joins the list" })).toBeInTheDocument();
  });

  it("keeps its title and description", () => {
    expect(metadata.title).toBe("F1 World Champions (1950–Present) | F1 AI");
    expect(metadata.description).toContain("Drivers' and Constructors' Champion since 1950");
  });
});
