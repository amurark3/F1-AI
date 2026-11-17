import { render, screen } from "@testing-library/react";
import { Suspense, isValidElement, type ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DIRECTORY_2026, PROFILE_PAGES_2026 } from "@/test/fixtures";

import TeamPage, { generateMetadata, generateStaticParams, revalidate } from "./page";
import { SeededTeamSwitch, SeededTeamView } from "./TeamSeeds";
import { TeamSwitch } from "./TeamSwitch";
import { TeamView } from "./TeamView";

const server = vi.hoisted(() => ({ getDirectory: vi.fn(), getTeamProfile: vi.fn() }));
const navigation = vi.hoisted(() => ({
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));

vi.mock("@/app/lib/server/profiles", () => server);
vi.mock("@/app/lib/server/raceControl", () => ({ currentSeason: () => 2026 }));
vi.mock("next/navigation", () => navigation);
vi.mock("./TeamSwitch", () => ({
  TeamSwitch: ({ teamId, seed }: { teamId: string; seed: unknown }) => (
    <p>{`switch ${teamId} ${seed ? "seeded" : "unseeded"}`}</p>
  ),
}));
vi.mock("./TeamView", () => ({
  TeamView: ({ teamId, seed }: { teamId: string; seed: unknown }) => (
    <p>{`view ${teamId} ${seed ? "seeded" : "unseeded"}`}</p>
  ),
}));

beforeEach(() => {
  server.getDirectory.mockReset();
  server.getTeamProfile.mockReset();
  navigation.notFound.mockClear();
});

describe("TeamPage", () => {
  it("awaits only its params and returns one Suspense boundary per section, each falling back to the unseeded client", async () => {
    const tree = (await TeamPage({ params: Promise.resolve({ team: "mercedes" }) })) as ReactElement<{
      children: [
        ReactElement<{ fallback: ReactElement; children: ReactElement }>,
        ReactElement<{ children: ReactElement<{ fallback: ReactElement; children: ReactElement }> }>,
      ];
    }>;

    const [switchBoundary, viewSlot] = tree.props.children;
    const viewBoundary = viewSlot.props.children;
    expect(switchBoundary?.type).toBe(Suspense);
    expect(switchBoundary?.props.fallback.type).toBe(TeamSwitch);
    expect(switchBoundary?.props.fallback.props).toEqual({ year: 2026, teamId: "mercedes", seed: null });
    expect(switchBoundary?.props.children.type).toBe(SeededTeamSwitch);
    expect(viewBoundary?.type).toBe(Suspense);
    expect(viewBoundary?.props.fallback.type).toBe(TeamView);
    expect(viewBoundary?.props.fallback.props).toEqual({ year: 2026, teamId: "mercedes", seed: null });
    expect(viewBoundary?.props.children.type).toBe(SeededTeamView);
    expect(server.getTeamProfile).not.toHaveBeenCalled();
    expect(server.getDirectory).not.toHaveBeenCalled();
  });

  it("revalidates every 15 minutes", () => {
    expect(revalidate).toBe(900);
  });
});

describe("SeededTeamSwitch", () => {
  it("seeds the switch with the directory, or leaves it unseeded when there is none", async () => {
    server.getDirectory.mockResolvedValue(DIRECTORY_2026);
    render(await SeededTeamSwitch({ year: 2026, teamId: "mercedes" }));
    expect(screen.getByText("switch mercedes seeded")).toBeInTheDocument();

    server.getDirectory.mockResolvedValue(null);
    render(await SeededTeamSwitch({ year: 2026, teamId: "mercedes" }));
    expect(screen.getByText("switch mercedes unseeded")).toBeInTheDocument();
  });
});

describe("SeededTeamView", () => {
  it("seeds the view with the profile", async () => {
    server.getTeamProfile.mockResolvedValue(PROFILE_PAGES_2026.mercedes);
    const element = await SeededTeamView({ year: 2026, teamId: "mercedes" });

    expect(isValidElement(element)).toBe(true);
    render(element);
    expect(screen.getByText("view mercedes seeded")).toBeInTheDocument();
  });

  it("calls notFound when the backend answered that the id is wrong", async () => {
    server.getTeamProfile.mockResolvedValue(PROFILE_PAGES_2026.unknown_team);

    await expect(SeededTeamView({ year: 2026, teamId: "lotus" })).rejects.toThrow("NEXT_NOT_FOUND");
    expect(navigation.notFound).toHaveBeenCalledTimes(1);
  });

  it("leaves the browser to fetch when the backend gave no answer", async () => {
    server.getTeamProfile.mockResolvedValue(null);
    render(await SeededTeamView({ year: 2026, teamId: "mercedes" }));

    expect(screen.getByText("view mercedes unseeded")).toBeInTheDocument();
  });
});

describe("generateMetadata", () => {
  it("titles the page from the directory, without waiting on the profile", async () => {
    server.getDirectory.mockResolvedValue(DIRECTORY_2026);
    const metadata = await generateMetadata({ params: Promise.resolve({ team: "mercedes" }) });

    expect(metadata.title).toBe("Mercedes AMG F1 — 2026 F1 Season | F1 AI");
    expect(String(metadata.description)).toContain("every driver's finish by round");
    expect(server.getTeamProfile).not.toHaveBeenCalled();
  });

  it.each([
    ["an unknown team", DIRECTORY_2026, "lotus"],
    ["no directory", null, "mercedes"],
  ])("falls back to the list's title for %s", async (_name, directory, team) => {
    server.getDirectory.mockResolvedValue(directory);

    expect((await generateMetadata({ params: Promise.resolve({ team }) })).title).toBe("F1 Teams | F1 AI");
  });
});

describe("generateStaticParams", () => {
  it("prerenders every team of the season by f1db id, and none without a directory", async () => {
    server.getDirectory.mockResolvedValue(DIRECTORY_2026);
    expect(await generateStaticParams()).toEqual(DIRECTORY_2026.teams.map((team) => ({ team: team.id })));

    server.getDirectory.mockResolvedValue(null);
    expect(await generateStaticParams()).toEqual([]);
  });
});
