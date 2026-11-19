import { beforeEach, describe, expect, it, vi } from "vitest";

import SeasonDetailPage, { generateMetadata, generateStaticParams } from "./page";
import { SeasonDetailView } from "./SeasonDetailView";

const champions = vi.hoisted(() => ({ getSeasonDetail: vi.fn(), listSeasonYears: vi.fn() }));

vi.mock("@/app/lib/server/champions", async (importActual) => ({
  ...(await importActual<Record<string, unknown>>()),
  ...champions,
}));
vi.mock("@/app/lib/server/raceControl", () => ({ currentSeason: () => 2026 }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

const params = (year: string) => ({ params: Promise.resolve({ year }) });

describe("the season page", () => {
  beforeEach(() => {
    champions.getSeasonDetail.mockReset().mockReturnValue(new Promise(() => undefined));
    champions.listSeasonYears.mockResolvedValue(["2026", "2025"]);
  });

  it("awaits only params and hands the view its seed", async () => {
    const page = await SeasonDetailPage(params("2026"));

    expect(page.type).toBe(SeasonDetailView);
    expect(page.props).toMatchObject({ year: 2026, latest: 2026 });
    expect(champions.getSeasonDetail).toHaveBeenCalledWith("2026");
  });

  it.each(["1949", "abc", "02026", "2027"])("404s %s without reading data", async (year) => {
    await expect(SeasonDetailPage(params(year))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(champions.getSeasonDetail).not.toHaveBeenCalled();
  });

  it("prerenders the recent seasons", async () => {
    expect(await generateStaticParams()).toEqual([{ year: "2026" }, { year: "2025" }]);
  });

  it("names the page without holding the stream", async () => {
    expect(await generateMetadata(params("2026"))).toEqual({
      title: "2026 F1 Season | F1 AI",
      description: "The 2026 Formula 1 World Champions and every race winner.",
    });
    expect(champions.getSeasonDetail).not.toHaveBeenCalled();
  });
});
