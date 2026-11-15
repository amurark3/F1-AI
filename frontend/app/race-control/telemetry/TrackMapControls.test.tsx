import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import mexicoLaps from "@/test/fixtures/qualifying-laps-mexico-2026.json";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { LAPS, SEGMENT_NOTICE_LAPS } from "./telemetryTestData";
import { TrackMapControls } from "./TrackMapControls";

import type { LapListResponse } from "./telemetryModel";

function renderControls(driver: string | null, lap: number | null = null) {
  server.use(http.get(apiUrl("/api/analysis/2026/20/laps"), () => HttpResponse.json(LAPS)));
  const onPick = vi.fn();
  const view = renderWithProviders(
    <TrackMapControls
      year={2026}
      round={20}
      session="Q"
      driver={driver}
      lap={lap}
      segment={null}
      onPick={onPick}
      onSegment={vi.fn()}
    />,
  );
  return { ...view, onPick };
}

describe("TrackMapControls", () => {
  it("offers the quickest driver and their laps, and reports a different driver with no lap", async () => {
    const { user, onPick } = renderControls(null);
    const driver = await screen.findByRole("combobox", { name: "Driver" });
    expect(driver).toHaveValue("ANT");
    await user.selectOptions(driver, "RUS");
    expect(onPick).toHaveBeenCalledWith("RUS", null);
  });

  it("reports a chosen lap, or none for the fastest valid lap", async () => {
    const { user, onPick } = renderControls("ANT", 14);
    const lap = await screen.findByRole("combobox", { name: "Lap" });
    expect(lap).toHaveValue("14");
    await user.selectOptions(lap, "15");
    expect(onPick).toHaveBeenLastCalledWith("ANT", 15);
    await user.selectOptions(lap, "");
    expect(onPick).toHaveBeenLastCalledWith("ANT", null);
  });

  it("shows nothing until the session's laps are in", () => {
    server.use(
      http.get(apiUrl("/api/analysis/2026/20/laps"), () => HttpResponse.json({ available: false, pending: true })),
    );
    const { container } = renderWithProviders(
      <TrackMapControls
        year={2026}
        round={20}
        session="Q"
        driver={null}
        lap={null}
        segment={null}
        onPick={vi.fn()}
        onSegment={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("TrackMapControls in qualifying", () => {
  function renderQualifying(
    driver: string | null,
    segment: number | null,
    laps: LapListResponse = mexicoLaps as unknown as LapListResponse,
  ) {
    server.use(http.get(apiUrl("/api/analysis/2026/19/laps"), () => HttpResponse.json(laps)));
    const onSegment = vi.fn();
    const view = renderWithProviders(
      <TrackMapControls
        year={2026}
        round={19}
        session="Q"
        driver={driver}
        lap={null}
        segment={segment}
        onPick={vi.fn()}
        onSegment={onSegment}
      />,
    );
    return { ...view, onSegment };
  }

  it("shows Q1 to Q3 on the last part reached, and reports a switch", async () => {
    const { user, onSegment } = renderQualifying("HUL", null);
    expect(await screen.findByRole("radio", { name: "Q2", checked: true })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Q3" }));
    expect(onSegment).toHaveBeenCalledWith(3);
  });

  it("opens on the quickest driver of the part", async () => {
    renderQualifying(null, 3);
    expect(await screen.findByRole("combobox", { name: "Driver" })).toHaveValue("HAM");
  });

  it("shows the backend's notice, with the pickers ungrouped, when the parts are not published", async () => {
    renderQualifying(null, null, SEGMENT_NOTICE_LAPS);
    expect(await screen.findByText("Q1/Q2/Q3 not published for this session")).toBeInTheDocument();
    expect(screen.queryAllByRole("group")).toHaveLength(0);
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });
});
