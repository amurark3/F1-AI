import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchFromBackend } from "./backend";
import { FIRST_SEASON, listSeasonYears, type ChampionsResponse, type SeasonChampion } from "./champions";

vi.mock("./backend", () => ({ fetchFromBackend: vi.fn() }));

const fetchMock = vi.mocked(fetchFromBackend);

/** The fields of a season `listSeasonYears` reads; the rest are filler. */
function season(year: number): SeasonChampion {
  return { season: year, is_in_progress: false, driver_champion: null, constructor_champion: null, round_count: 0 };
}

/** 1950 to 2026, in the order the backend lists them (oldest first). */
const EVERY_SEASON: SeasonChampion[] = Array.from({ length: 2026 - FIRST_SEASON + 1 }, (_, i) =>
  season(FIRST_SEASON + i),
);

describe("listSeasonYears", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("lists every season the archive knows, newest first, so each one is prerendered", async () => {
    fetchMock.mockResolvedValue({ seasons: EVERY_SEASON } satisfies ChampionsResponse);

    const years = await listSeasonYears();

    expect(years).toHaveLength(77);
    expect(years.slice(0, 2)).toEqual(["2026", "2025"]);
    expect(years.at(-1)).toBe("1950");
  });

  it("lists nothing when the backend is unreachable at build time, leaving every season to render on demand", async () => {
    fetchMock.mockResolvedValue(null);

    await expect(listSeasonYears()).resolves.toEqual([]);
  });
});
