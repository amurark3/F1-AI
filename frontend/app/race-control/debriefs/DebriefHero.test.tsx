import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { DebriefHero } from "./DebriefHero";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const R19 = DEBRIEF_R19.summary;

describe("DebriefHero", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("headlines the win and the title, and lists the podium with how each car started", async () => {
    renderWithProviders(<DebriefHero summary={R19} />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Verstappen wins the Mexican Grand Prix; Antonelli is champion",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Race debrief · Round 19 · Mexican Grand Prix")).toBeInTheDocument();
    expect(screen.queryByText("Provisional")).not.toBeInTheDocument();

    const podium = screen.getByRole("group", { name: "Podium" });
    expect(within(podium).getByText("2:20:28.772 · from P5")).toBeInTheDocument();
    expect(within(podium).getByText("+0.799 · from pole")).toBeInTheDocument();
    expect(within(podium).getByText("+4.006 · from P4")).toBeInTheDocument();
    expect(podium.querySelectorAll("[data-step]")).toHaveLength(3);
  });

  it("marks a provisional result", async () => {
    renderWithProviders(<DebriefHero summary={{ ...R19, final: false }} />);

    expect(await screen.findByText("Provisional")).toBeInTheDocument();
  });

  it("shows no start for a car without a grid slot, and a podium of fewer than three", () => {
    const [winner, second] = R19.classification;
    renderWithProviders(
      <DebriefHero
        summary={{
          ...R19,
          classification: [
            { ...winner, grid: null },
            { ...second, gap: null },
          ],
        }}
      />,
    );

    const podium = screen.getByRole("group", { name: "Podium" });
    expect(within(podium).getByText("2:20:28.772")).toBeInTheDocument();
    expect(podium.querySelectorAll("[data-step]")).toHaveLength(2);
  });

  it("gives the reason, and no podium, when the race is not classified", () => {
    renderWithProviders(
      <DebriefHero
        summary={{ ...R19, available: false, reason: "The race hasn't been classified yet.", classification: [] }}
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Mexican Grand Prix" })).toBeInTheDocument();
    expect(screen.getByText("The race hasn't been classified yet.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Podium" })).not.toBeInTheDocument();
    expect(screen.queryByText("Provisional")).not.toBeInTheDocument();
  });

  it("draws no podium for a classification with no winner", () => {
    renderWithProviders(<DebriefHero summary={{ ...R19, classification: [] }} />);

    expect(screen.queryByRole("group", { name: "Podium" })).not.toBeInTheDocument();
  });
});
