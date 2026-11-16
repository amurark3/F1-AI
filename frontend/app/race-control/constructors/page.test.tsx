import { render, screen } from "@testing-library/react";
import { Suspense, isValidElement, type ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import ConstructorsPage, { metadata, revalidate } from "./page";
import { TeamsIndexSeed } from "./TeamsIndexSeed";
import { TeamsIndexView } from "./TeamsIndexView";

const server = vi.hoisted(() => ({ getTeamsIndex: vi.fn() }));

vi.mock("@/app/lib/server/profiles", () => server);
vi.mock("@/app/lib/server/raceControl", () => ({ currentSeason: () => 2026 }));
vi.mock("./TeamsIndexView", () => ({
  TeamsIndexView: ({ year, seed }: { year: number; seed: unknown }) => (
    <p>{`view ${year} ${seed ? "seeded" : "unseeded"}`}</p>
  ),
}));

beforeEach(() => {
  server.getTeamsIndex.mockReset();
});

describe("ConstructorsPage", () => {
  it("returns a Suspense boundary whose fallback is the unseeded view, without awaiting the backend", () => {
    const tree = ConstructorsPage() as ReactElement<{ fallback: ReactElement; children: ReactElement }>;

    expect(tree.type).toBe(Suspense);
    expect(tree.props.fallback.type).toBe(TeamsIndexView);
    expect(tree.props.fallback.props).toEqual({ year: 2026, seed: null });
    expect(tree.props.children.type).toBe(TeamsIndexSeed);
    expect(server.getTeamsIndex).not.toHaveBeenCalled();
  });

  it("revalidates every 15 minutes and describes the index without power units", () => {
    expect(revalidate).toBe(900);
    expect(metadata.title).toBe("F1 Teams | F1 AI");
    expect(String(metadata.description)).not.toMatch(/power/i);
  });
});

describe("TeamsIndexSeed", () => {
  it("seeds the view with an ok payload", async () => {
    server.getTeamsIndex.mockResolvedValue(PROFILE_PAGES_2026.teams_index);
    const element = await TeamsIndexSeed({ year: 2026 });

    expect(isValidElement(element)).toBe(true);
    render(element);
    expect(screen.getByText("view 2026 seeded")).toBeInTheDocument();
  });

  it.each([
    ["no answer", null],
    ["an error payload", { year: 2026, status: "error" }],
  ])("leaves the view unseeded on %s", async (_name, answer) => {
    server.getTeamsIndex.mockResolvedValue(answer);
    render(await TeamsIndexSeed({ year: 2026 }));

    expect(screen.getByText("view 2026 unseeded")).toBeInTheDocument();
  });
});
