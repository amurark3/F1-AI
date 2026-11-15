import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, PREDICTION_REVIEW_R19 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { PodiumPanel } from "./OrderPanels";
import { ModelIO, RiskTable } from "./RiskModelPanels";

const [BOTTAS] = PREDICTION_REVIEW_R19.risk_predictions!.filter((row) => row.driver_code === "BOT");

describe("the Risk and Model views", () => {
  beforeEach(() => {
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("names a risk row's first signal, or its level when it has none", () => {
    renderWithProviders(
      <RiskTable rows={[BOTTAS, { ...BOTTAS, driver_code: "XXX", factors: [], risk_level: "high" }]} />,
    );

    expect(screen.getByText("9 DNF events in recent history")).toBeVisible();
    expect(screen.getByText("high")).toBeVisible();
  });

  it("falls back to the manual-compute policy and zero counts for an empty snapshot", () => {
    renderWithProviders(<ModelIO />);

    expect(screen.getByText("manual compute")).toBeVisible();
    expect(screen.getAllByText("0 drivers")).toHaveLength(2);
  });

  it("reads the stored policy and snapshot count", () => {
    renderWithProviders(
      <ModelIO
        data={{
          ...PREDICTION_REVIEW_R19,
          cache: { status: "hit", policy: "frozen after qualifying", snapshot_count: 3 },
        }}
      />,
    );

    expect(screen.getByText("frozen after qualifying")).toBeVisible();
    expect(screen.getByText("3")).toBeVisible();
  });
});

describe("PodiumPanel", () => {
  beforeEach(() => {
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("asks for a run when there is no podium yet", () => {
    renderWithProviders(<PodiumPanel podium={[]} driverLookup={{}} />);

    expect(screen.getByText("Run the model to create a podium snapshot.")).toBeVisible();
    expect(screen.getByText("-% confidence")).toBeVisible();
  });

  it("shows the called podium with its model-summary confidence and the leader's attribution", () => {
    const podium = PREDICTION_REVIEW_R19.predictions.slice(0, 3);
    renderWithProviders(
      <PodiumPanel
        podium={podium}
        driverLookup={{}}
        data={{ ...PREDICTION_REVIEW_R19, model_summary: { average_top3_confidence: 81 } }}
      />,
    );

    expect(screen.getByText("81% confidence")).toBeVisible();
    expect(screen.getByText(/Why the model picks/)).toBeVisible();
  });

  it("leaves out the why-panel for a leader with no stored attribution", () => {
    const podium = PREDICTION_REVIEW_R19.predictions.slice(0, 3).map((row) => ({ ...row, model_attribution: null }));
    renderWithProviders(<PodiumPanel podium={podium} driverLookup={{}} />);

    expect(screen.queryByText(/Why the model picks/)).not.toBeInTheDocument();
  });
});
