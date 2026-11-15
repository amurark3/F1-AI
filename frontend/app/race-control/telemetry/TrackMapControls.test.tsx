import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { LAPS } from "./telemetryTestData";
import { TrackMapControls } from "./TrackMapControls";

function renderControls(driver: string | null, lap: number | null = null) {
  server.use(http.get(apiUrl("/api/analysis/2026/20/laps"), () => HttpResponse.json(LAPS)));
  const onPick = vi.fn();
  const view = renderWithProviders(
    <TrackMapControls year={2026} round={20} session="Q" driver={driver} lap={lap} onPick={onPick} />,
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
      <TrackMapControls year={2026} round={20} session="Q" driver={null} lap={null} onPick={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
