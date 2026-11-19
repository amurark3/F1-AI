import { beforeEach, describe, expect, it, vi } from "vitest";

import { POWER_UNITS_2026 } from "@/test/fixtures";

import CarPage, { generateMetadata, generateStaticParams, revalidate } from "./page";

const raceControl = vi.hoisted(() => ({ getPowerUnits: vi.fn() }));

vi.mock("@/app/lib/server/raceControl", () => ({ ...raceControl, currentSeason: () => 2026 }));

const params = (car: string) => ({ params: Promise.resolve({ car }) });

beforeEach(() => {
  raceControl.getPowerUnits.mockResolvedValue(POWER_UNITS_2026);
});

describe("the car page", () => {
  it("awaits only its params: a payload that never arrives does not hold it", async () => {
    raceControl.getPowerUnits.mockReturnValue(new Promise(() => undefined));

    const element = await CarPage(params("6"));

    expect(element.props).toMatchObject({ year: 2026, segment: "6" });
    expect(raceControl.getPowerUnits).toHaveBeenCalledWith(2026);
  });

  it("revalidates every five minutes", () => {
    expect(revalidate).toBe(300);
  });

  it("prerenders every car by its number", async () => {
    const all = await generateStaticParams();

    expect(all).toHaveLength(POWER_UNITS_2026.cars.length);
    expect(all).toContainEqual({ car: "6" });
  });

  it("prerenders nothing without a payload", async () => {
    raceControl.getPowerUnits.mockResolvedValue(null);

    expect(await generateStaticParams()).toEqual([]);
  });
});

describe("generateMetadata", () => {
  it("titles the page by number and driver", async () => {
    expect(await generateMetadata(params("6"))).toMatchObject({
      title: "#6 Isack Hadjar — Power Units | F1 AI",
    });
  });

  it("keeps an unknown car out of the index", async () => {
    const metadata = await generateMetadata(params("99"));

    expect(metadata.title).toBe("Power Unit Tracker | F1 AI");
    expect(metadata.robots).toMatchObject({ index: false });
  });

  it("falls back to the plain title with no payload", async () => {
    raceControl.getPowerUnits.mockResolvedValue(null);

    const metadata = await generateMetadata(params("6"));

    expect(metadata.title).toBe("Power Unit Tracker | F1 AI");
    expect(metadata.robots).toBeUndefined();
  });

  it("does not call the car unknown when the season is not collected", async () => {
    raceControl.getPowerUnits.mockResolvedValue({ ...POWER_UNITS_2026, available: false, cars: [] });

    expect((await generateMetadata(params("6"))).robots).toBeUndefined();
  });
});
