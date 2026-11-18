import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import {
  DIRECTORY_2026,
  GRIDS_2026,
  PREDICTION_REVIEW_R19,
  RACE_RESULTS_2026,
  SEASON_2026,
  WEEKEND_SESSIONS_2026,
} from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { GrandPrixView } from "./GrandPrixView";

import type { HubSelection } from "./hubNavigation";
import type { GrandPrixSeed } from "./hubSeed";
import type { PredictionsResponse } from "./predictionModel";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const SNAPSHOT_URL = apiUrl("/api/predictions/2026/:round/snapshot");
const POST: PredictionsResponse = PREDICTION_REVIEW_R19;
const PRE: PredictionsResponse = {
  ...POST,
  prediction_phase: "pre_qualifying",
  prediction_review: { evaluated: false, reason: "Actual race result is not available yet." },
  cache: { status: "hit", stored_at: "2026-10-30T10:00:00Z", snapshot_id: "r19-pre" },
};

function seed(changes: Partial<GrandPrixSeed> = {}): GrandPrixSeed {
  return {
    year: 2026,
    schedule: SEASON_2026.schedule,
    drivers: { drivers: [] },
    snapshots: { pre_qualifying: PRE, post_qualifying: POST },
    snapshotRound: 19,
    grid: GRIDS_2026.mexicoCityOfficial,
    sessions: WEEKEND_SESSIONS_2026.mexicoCity,
    strategy: null,
    ...changes,
  };
}

function Harness({ initial, seedValue }: { initial: HubSelection; seedValue: GrandPrixSeed }) {
  const [selection, setSelection] = useState(initial);
  return (
    <GrandPrixView
      seed={seedValue}
      url={{ ...selection, update: (changes) => setSelection((current) => ({ ...current, ...changes })) }}
    />
  );
}

function open(view: HubSelection["view"], seedValue = seed(), round = 19) {
  return renderWithProviders(<Harness initial={{ round, tab: "predictions", view }} seedValue={seedValue} />);
}

function answerSnapshots(post: unknown = POST, pre: unknown = PRE, status = 200) {
  server.use(
    http.get(SNAPSHOT_URL, ({ request }) =>
      HttpResponse.json(
        (new URL(request.url).searchParams.get("phase") === "post_qualifying" ? post : pre) as Record<string, unknown>,
        { status },
      ),
    ),
  );
}

describe("the Predictions tab (Mexico City)", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(apiUrl("/api/schedule/2026"), () => HttpResponse.json(SEASON_2026.schedule)),
      http.get(apiUrl("/api/race-control/drivers/2026"), () => HttpResponse.json({ drivers: [] })),
      http.get(apiUrl("/api/race-control/grid/2026/:round"), () => HttpResponse.json(GRIDS_2026.mexicoCityOfficial)),
      http.get(apiUrl("/api/race-control/sessions/2026/:round"), () =>
        HttpResponse.json(WEEKEND_SESSIONS_2026.mexicoCity),
      ),
      http.get(apiUrl("/api/race-control/results/2026/:round"), () => HttpResponse.json(RACE_RESULTS_2026.mexicoCity)),
      http.get(apiUrl("/api/champions/2026"), () => HttpResponse.json(SEASON_2026.winners)),
    );
    answerSnapshots();
  });

  it("opens the Order on the after-qualifying call, with vs grid and no removed columns", async () => {
    open("order");

    expect(await screen.findByText("Predicted order · 22 cars")).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "vs grid" })).toBeVisible();
    expect(screen.queryByRole("columnheader", { name: "Pts" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /After Qualifying/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("drops vs grid on the before-qualifying tab", async () => {
    const { user } = open("order");
    await screen.findByText("Predicted order · 22 cars");

    await user.click(screen.getByRole("button", { name: /Overall/ }));

    await waitFor(() => expect(screen.queryByRole("columnheader", { name: "vs grid" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Overall/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("scores the call on the Review view: DNF rows with reasons, no place delta, no results table", async () => {
    open("review");

    const lindblad = (await screen.findByText(/Collision · 58 laps · risk 13%/)).closest("li")!;
    expect(within(lindblad).getByText("DNF")).toBeVisible();
    expect(lindblad).not.toHaveTextContent(/[+−]\d/);
    expect(screen.getByText("2/3")).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("moves between the views without leaving the tab", async () => {
    const { user } = open("order");
    await screen.findByText("Predicted order · 22 cars");

    await user.click(screen.getByRole("tab", { name: "Podium" }));
    expect(await screen.findByText("Predicted podium")).toBeVisible();

    await user.click(screen.getByRole("tab", { name: "DNF / Crash" }));
    expect(await screen.findByText("DNF and crash model")).toBeVisible();

    await user.click(screen.getByRole("tab", { name: "Model" }));
    expect(await screen.findByText("No model input coverage returned for this snapshot.")).toBeVisible();
    expect(screen.getAllByText("22 drivers")).toHaveLength(2);

    await user.click(screen.getByRole("tab", { name: "Review" }));
    expect(await screen.findByText("Call against result")).toBeVisible();
  });

  it("explains an empty phase as not published yet, with no way to run it", async () => {
    answerSnapshots({ predictions: [] }, { predictions: [] });
    open("order", seed({ snapshots: { pre_qualifying: null, post_qualifying: null } }));

    expect(await screen.findByText(/No stored overall prediction for/)).toBeVisible();
    expect(screen.getByText(/has not been published yet/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /run/i })).not.toBeInTheDocument();
  });

  it("offers to check again when a snapshot cannot be loaded", async () => {
    answerSnapshots({ detail: "x" }, { detail: "x" }, 500);
    const { user } = open("order", seed({ snapshots: { pre_qualifying: null, post_qualifying: null } }));

    expect(await screen.findByText("No Overall Snapshot")).toBeVisible();
    answerSnapshots();
    await user.click(screen.getByRole("button", { name: "check again" }));
    expect(await screen.findByText("Predicted order · 22 cars")).toBeVisible();
  });

  it("keeps the after-qualifying tab locked until qualifying has run", async () => {
    const upcoming = SEASON_2026.schedule.find((race) => race.status === "upcoming")!;
    answerSnapshots({ predictions: [] }, { predictions: [] });
    const { user } = open(
      "order",
      seed({ snapshots: { pre_qualifying: null, post_qualifying: null }, snapshotRound: upcoming.round }),
      upcoming.round,
    );

    await user.click(await screen.findByRole("button", { name: /After Qualifying/ }));

    expect(await screen.findByText("Qualifying Has Not Run")).toBeVisible();
  });

  it("shows the prediction's own warnings", async () => {
    answerSnapshots({ ...POST, warnings: ["Seat TBC: Haas car 2", "second", "third"] });
    open("order");

    expect(await screen.findByText("Seat TBC: Haas car 2 second")).toBeVisible();
  });
  it("shows the model's why on the Podium view from the stored attribution", async () => {
    const { user } = open("podium");

    expect(await screen.findByText("Predicted podium")).toBeVisible();
    expect(await screen.findByText(/Why the model picks/)).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Order" }));
    expect(await screen.findByText("Predicted order · 22 cars")).toBeVisible();
  });

  it("lists what the model was fed when the snapshot says so", async () => {
    answerSnapshots({
      ...POST,
      model_inputs: [
        { label: "Qualifying", status: "available", impact: "Sets the grid.", source: "FIA" },
        { label: "Weather", status: "fallback", impact: "Dry assumed.", source: "Open-Meteo" },
      ],
    });
    open("model");

    expect(await screen.findByText("Qualifying")).toBeVisible();
    expect(screen.getByText("fallback")).toBeVisible();
  });

  it("steps to another round from the picker", async () => {
    const { user } = open("order");
    await screen.findByText("Predicted order · 22 cars");

    await user.click(screen.getByRole("button", { name: "Previous round" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Next round" })).toBeEnabled());
  });

  it("shows a risk-less snapshot's empty risk table", async () => {
    answerSnapshots({ ...POST, risk_predictions: [] });
    open("risk");

    expect(await screen.findByText(/Run or recompute the model to generate DNF/)).toBeVisible();
  });
});
