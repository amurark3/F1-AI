import { render, screen } from "@testing-library/react";
import { Suspense, isValidElement, type ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DIRECTORY_2026, PROFILE_PAGES_2026 } from "@/test/fixtures";

import { SeededDriverView } from "./DriverSeed";
import { DriverView } from "./DriverView";
import DriverPage, { generateMetadata, generateStaticParams, revalidate } from "./page";

const server = vi.hoisted(() => ({ getDirectory: vi.fn(), getDriverProfile: vi.fn() }));
const navigation = vi.hoisted(() => ({
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));

vi.mock("@/app/lib/server/profiles", () => server);
vi.mock("@/app/lib/server/raceControl", () => ({ currentSeason: () => 2026 }));
vi.mock("next/navigation", () => navigation);
vi.mock("./DriverView", () => ({
  DriverView: ({ driverId, seed }: { driverId: string; seed: unknown }) => (
    <p>{`view ${driverId} ${seed ? "seeded" : "unseeded"}`}</p>
  ),
}));

beforeEach(() => {
  server.getDirectory.mockReset();
  server.getDriverProfile.mockReset();
  navigation.notFound.mockClear();
});

describe("DriverPage", () => {
  it("awaits only its params and returns one Suspense boundary, falling back to the unseeded client", async () => {
    const tree = (await DriverPage({ params: Promise.resolve({ driver: "lewis-hamilton" }) })) as ReactElement<{
      fallback: ReactElement;
      children: ReactElement;
    }>;

    expect(tree.type).toBe(Suspense);
    expect(tree.props.fallback.type).toBe(DriverView);
    expect(tree.props.fallback.props).toEqual({ year: 2026, driverId: "lewis-hamilton", seed: null });
    expect(tree.props.children.type).toBe(SeededDriverView);
    expect(server.getDriverProfile).not.toHaveBeenCalled();
    expect(server.getDirectory).not.toHaveBeenCalled();
  });

  it("revalidates every 15 minutes", () => {
    expect(revalidate).toBe(900);
  });
});

describe("SeededDriverView", () => {
  it("seeds the view with the profile", async () => {
    server.getDriverProfile.mockResolvedValue(PROFILE_PAGES_2026.hamilton);
    const element = await SeededDriverView({ year: 2026, driverId: "lewis-hamilton" });

    expect(isValidElement(element)).toBe(true);
    render(element);
    expect(screen.getByText("view lewis-hamilton seeded")).toBeInTheDocument();
  });

  it("calls notFound when the backend answered that the id is wrong", async () => {
    server.getDriverProfile.mockResolvedValue({ year: 2026, status: "not_found", driver: null });

    await expect(SeededDriverView({ year: 2026, driverId: "nobody" })).rejects.toThrow("NEXT_NOT_FOUND");
    expect(navigation.notFound).toHaveBeenCalledTimes(1);
  });

  it("leaves the browser to fetch when the backend gave no answer", async () => {
    server.getDriverProfile.mockResolvedValue(null);
    render(await SeededDriverView({ year: 2026, driverId: "lewis-hamilton" }));

    expect(screen.getByText("view lewis-hamilton unseeded")).toBeInTheDocument();
  });
});

describe("generateMetadata", () => {
  it("titles the page from the directory, without waiting on the profile", async () => {
    server.getDirectory.mockResolvedValue(DIRECTORY_2026);
    const metadata = await generateMetadata({ params: Promise.resolve({ driver: "max-verstappen" }) });

    expect(metadata.title).toBe("Max Verstappen — 2026 F1 Season | F1 AI");
    expect(String(metadata.description)).toContain("with Red Bull");
    expect(server.getDriverProfile).not.toHaveBeenCalled();
  });

  it("names no team when the directory does not list the driver's", async () => {
    server.getDirectory.mockResolvedValue({ ...DIRECTORY_2026, teams: [] });
    const metadata = await generateMetadata({ params: Promise.resolve({ driver: "max-verstappen" }) });

    expect(String(metadata.description)).toContain("with its team");
  });

  it.each([
    ["an unknown driver", DIRECTORY_2026, "nobody"],
    ["no directory", null, "max-verstappen"],
  ])("falls back to a plain title for %s", async (_name, directory, driver) => {
    server.getDirectory.mockResolvedValue(directory);

    expect((await generateMetadata({ params: Promise.resolve({ driver }) })).title).toBe("F1 Drivers | F1 AI");
  });
});

describe("generateStaticParams", () => {
  it("prerenders every driver of the season by f1db id, and none without a directory", async () => {
    server.getDirectory.mockResolvedValue(DIRECTORY_2026);
    expect(await generateStaticParams()).toEqual(DIRECTORY_2026.drivers.map((driver) => ({ driver: driver.id })));

    server.getDirectory.mockResolvedValue(null);
    expect(await generateStaticParams()).toEqual([]);
  });
});
