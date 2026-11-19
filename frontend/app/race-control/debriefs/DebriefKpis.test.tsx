import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import type { SectionState } from "@/app/ui/section/sectionState";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { DebriefKpis } from "./DebriefKpis";

import type { DebriefOvertakes, DebriefSummary } from "./debriefTypes";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const R19 = DEBRIEF_R19.summary;
const retry = vi.fn();

function state(status: SectionState["status"], reason: string | null = null): SectionState {
  return { status, reason, refreshing: false, retry };
}

function renderKpis(summary: DebriefSummary, status: SectionState["status"] = "ready", data?: DebriefOvertakes) {
  return renderWithProviders(
    <DebriefKpis
      summary={summary}
      overtakes={{ ...state(status, status === "failed" || status === "stale" ? "HTTP 500" : null), data }}
    />,
  );
}

function tile(label: string): HTMLElement {
  return screen.getByRole("group", { name: label }).closest("div")!;
}

describe("DebriefKpis", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("shows Mexico City's margin, position changes, biggest climb and retirements", async () => {
    renderKpis(R19, "ready", DEBRIEF_R19.overtakes);

    expect(await screen.findByText("Verstappen over Hamilton")).toBeInTheDocument();
    expect(screen.getByText("0.799")).toBeInTheDocument();
    expect(screen.getByText("273")).toBeInTheDocument();
    expect(screen.getByText("on-track position changes · OpenF1")).toBeInTheDocument();
    expect(screen.getByText("+15")).toBeInTheDocument();
    expect(screen.getByText("Lawson · pit lane → P7")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Lindblad L58, Bearman L47, Bottas L42, Stroll & Alonso L5")).toBeInTheDocument();
  });

  it("reads a climb from a grid slot", async () => {
    renderKpis({ ...R19, classification: [{ ...R19.classification[0], grid: 4 }] });

    expect(await screen.findByText("Verstappen · P4 → P1")).toBeInTheDocument();
  });

  it("says why there is no climb: no official grid, or nobody gained", () => {
    renderKpis({ ...R19, grid: { available: false, fia_document: null } });
    expect(screen.getByText("Waiting for the official starting grid")).toBeInTheDocument();
  });

  it("says nobody gained, and that there were no retirements or margin", () => {
    renderKpis({ ...R19, classification: [{ ...R19.classification[0], grid: 1 }] });

    expect(screen.getByText("No driver gained places")).toBeInTheDocument();
    expect(screen.getByText("No retirements")).toBeInTheDocument();
    expect(screen.getByText("No winning margin to state")).toBeInTheDocument();
  });

  it("holds the position-changes tile quiet while it loads", () => {
    renderKpis(R19, "pending");

    expect(tile("Overtakes")).toHaveTextContent("—");
    expect(screen.queryByText("on-track position changes · OpenF1")).not.toBeInTheDocument();
  });

  it("says unavailable, with a retry, when the position changes failed", async () => {
    const { user } = renderKpis(R19, "failed");

    expect(tile("Overtakes")).toHaveTextContent("Unavailable");
    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalled();
  });

  it("keeps the figure on screen, marked stale, when a refresh failed", () => {
    renderKpis(R19, "stale", DEBRIEF_R19.overtakes);

    expect(screen.getByText("273")).toBeInTheDocument();
    expect(screen.getByText("Couldn't refresh")).toBeInTheDocument();
  });

  it("says OpenF1 has none when the race has no position changes", () => {
    renderKpis(R19, "ready", { available: false, total: 0, drivers: [] });

    expect(screen.getByText("OpenF1 has no position changes for this race")).toBeInTheDocument();
  });
});
