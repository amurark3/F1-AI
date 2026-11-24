import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchFromBackend } from "./backend";
import {
  getChampions,
  getChampionStats,
  getLatestChampion,
  getSeasonDetail,
  listSeasonYears,
  type ChampionsResponse,
} from "./champions";
import { REVALIDATE } from "./revalidate";

vi.mock("./backend", () => ({ fetchFromBackend: vi.fn() }));

const fetchMock = vi.mocked(fetchFromBackend);

const archive = (tags: string[]) => ({ revalidate: REVALIDATE.ARCHIVE, tags });

describe("champions reads", () => {
  beforeEach(() => {
    fetchMock.mockResolvedValue(null);
  });

  it("asks for the season list, the latest champion and the title leaderboards", async () => {
    await getChampions();
    await getLatestChampion();
    await getChampionStats();

    expect(fetchMock.mock.calls).toEqual([
      ["/api/champions", archive(["champions"])],
      ["/api/champions/latest", archive(["champions"])],
      ["/api/champions/stats", archive(["champions"])],
    ]);
  });

  it("tags one season's detail so it can be revalidated alone", async () => {
    await getSeasonDetail("1988");

    expect(fetchMock).toHaveBeenCalledWith("/api/champions/1988", archive(["champions", "champions:1988"]));
  });
});

describe("listSeasonYears", () => {
  const season = (year: number) => ({ season: year }) as NonNullable<ChampionsResponse["seasons"]>[number];

  it("lists the newest twelve seasons first", async () => {
    const seasons = Array.from({ length: 20 }, (_, index) => season(2000 + index));
    fetchMock.mockResolvedValue({ seasons });

    const years = await listSeasonYears();

    expect(years).toEqual(Array.from({ length: 12 }, (_, index) => String(2019 - index)));
  });

  it.each([
    ["the backend is unreachable", null],
    ["the response carries no seasons", {}],
  ])("is empty when %s", async (_name, response) => {
    fetchMock.mockResolvedValue(response);

    await expect(listSeasonYears()).resolves.toEqual([]);
  });
});
