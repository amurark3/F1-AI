import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, PREDICTION_REVIEW_R19, RACE_RESULTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { ResultsReview } from "./PredictionResultsReview";

import type { PredictionReview } from "./predictionModel";

const REVIEW = PREDICTION_REVIEW_R19.prediction_review!;

function show(review: PredictionReview | undefined = REVIEW, round: number | null = 19) {
  return renderWithProviders(
    <ResultsReview
      review={review}
      accuracy={PREDICTION_REVIEW_R19.accuracy}
      predictions={PREDICTION_REVIEW_R19.predictions}
      driverLookup={{}}
      year={2026}
      round={round}
    />,
  );
}

describe("ResultsReview (Mexico City, the real stored review)", () => {
  beforeEach(() => {
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(apiUrl("/api/race-control/results/2026/19"), () => HttpResponse.json(RACE_RESULTS_2026.mexicoCity)),
    );
  });

  it("scores the call: winner, podium, top ten and the average miss over 17 classified cars", async () => {
    show();

    expect(await screen.findByText("Right")).toHaveClass("text-rc-gold");
    expect(screen.getByText("2/3")).toBeInTheDocument();
    expect(screen.getByText("8/10")).toBeInTheDocument();
    expect(screen.getByText("3.2")).toBeInTheDocument();
    expect(screen.getByText("over 17 classified cars · 2 exact · 10 within 3")).toBeInTheDocument();
  });

  it("says the result is provisional until the stored result is final", async () => {
    show();

    expect(
      await screen.findByText("Scored against the provisional result; it is scored again when the final lands"),
    ).toBeInTheDocument();
    expect(screen.getByText("Provisional")).toBeInTheDocument();
  });

  it("reads Final once the stored result is final", async () => {
    show({ ...REVIEW, actual_provisional: false });

    expect(await screen.findByText("The final classification")).toBeInTheDocument();
    expect(screen.getByText("Final")).toBeInTheDocument();
  });

  it("draws a DNF row with its reason, the risk call and no place delta", async () => {
    show();

    const lindblad = (await screen.findByText(/Collision · 58 laps · risk 13%, under the 16% flag/)).closest("li")!;
    expect(within(lindblad).getByText("DNF")).toHaveClass("text-rc-red-text");
    expect(lindblad).toHaveTextContent("no place delta");
    expect(lindblad).not.toHaveTextContent(/called P8, finished/);
    expect(lindblad).not.toHaveTextContent(/[+−]\d/);
  });

  it("gives a classified car its signed place delta, neutral ink", async () => {
    show();

    const hamilton = (await screen.findByText("Hamilton")).closest("li")!;
    expect(within(hamilton).getByText("+2")).toHaveClass("text-rc-ink-2");
    expect(hamilton).toHaveTextContent("called P4, finished P2");
    const leclerc = screen.getByText("Leclerc").closest("li")!;
    expect(within(leclerc).getByText("−2")).toBeInTheDocument();
    const verstappen = screen.getByText("Verstappen").closest("li")!;
    expect(within(verstappen).getByText("0")).toBeInTheDocument();
  });

  it("titles the chart and the retirement panel from the data", async () => {
    show();

    expect(await screen.findByRole("heading", { name: "Bortoleto and Albon beat the call by 7 places" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "The risk model flagged 4 of the 5 retirements" })).toBeVisible();
    expect(screen.getByText(/10 cars were flagged; 4 of them retired/)).toHaveTextContent(
      "crash risk caught 1 of 3 incidents",
    );
  });

  it("lists each retirement with its risk and whether it was flagged", async () => {
    show();

    const panel = (await screen.findByRole("heading", { name: /flagged 4 of the 5/ })).closest("section")!;
    const rows = within(panel).getAllByRole("listitem");
    expect(rows).toHaveLength(5);
    expect(rows[0]).toHaveTextContent("Bottas");
    expect(rows[0]).toHaveTextContent("36%");
    expect(rows[0]).toHaveTextContent("flagged");
    expect(rows[4]).toHaveTextContent("Lindblad");
    expect(rows[4]).toHaveTextContent("not flagged");
  });

  it("prints no results table and links to the final classification", async () => {
    show();

    await screen.findByText("Right");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText(/Predicted vs actual/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Final classification" })).toHaveAttribute(
      "href",
      "/race-control/grand-prix?round=19&tab=results&year=2026",
    );
  });

  it("still draws the chart before Results answers, with the status in place of a reason", async () => {
    server.use(
      http.get(apiUrl("/api/race-control/results/2026/19"), () =>
        HttpResponse.json({ error: "down" }, { status: 503 }),
      ),
    );
    show();

    expect(await screen.findByText(/^DNF · risk 13%, under the 16% flag/)).toBeInTheDocument();
  });

  it("shows the rolling accuracy when the race has no review yet", () => {
    show({ evaluated: false, reason: "Actual race result is not available yet." });

    expect(screen.getByText("Actual race result is not available yet.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "The last 8 scored races" })).toBeVisible();
    expect(screen.getByText("52%")).toBeInTheDocument();
  });

  it("falls back to dashes and a default sentence with no accuracy and no review", () => {
    renderWithProviders(<ResultsReview predictions={[]} driverLookup={{}} year={2026} round={null} />);

    expect(screen.getByText("This race has not been scored against a result yet.")).toBeInTheDocument();
    expect(screen.getByText("n/a")).toBeInTheDocument();
  });

  it("names a substitute from the standings when the snapshot does not hold the driver", async () => {
    renderWithProviders(
      <ResultsReview
        review={REVIEW}
        predictions={PREDICTION_REVIEW_R19.predictions.filter((row) => row.driver_code !== "VER")}
        driverLookup={{
          VER: { code: "VER", name: "Max Verstappen", team: "Red Bull Racing", position: 1, points: 1, wins: 1 },
        }}
        year={2026}
        round={19}
      />,
    );

    expect(await screen.findByText("Verstappen")).toBeInTheDocument();
  });
  it("reads a sparse review: no per-car risk figures, no counts, no accuracy figures", async () => {
    const sparse: PredictionReview = {
      evaluated: true,
      winner_correct: false,
      predicted_winner: "VER",
      actual_winner: "LEC",
      driver_results: [
        {
          driver_code: "VER",
          predicted_position: 1,
          actual_position: 3,
          position_delta: 2,
          exact: false,
          status: "Finished",
          dnf: false,
          crash: false,
        },
        {
          driver_code: "BOT",
          predicted_position: 2,
          actual_position: null,
          position_delta: null,
          exact: false,
          status: "DNF",
          dnf: true,
          crash: false,
        },
        {
          driver_code: "STR",
          predicted_position: 3,
          actual_position: null,
          position_delta: null,
          exact: false,
          status: "DNF",
          dnf: true,
          crash: false,
          predicted_dnf_risk_pct: 30,
        },
      ],
    };
    show(sparse);

    expect(await screen.findByText("Missed")).toBeVisible();
    expect(screen.getByText(/no risk figure stored/)).toBeVisible();
    expect(screen.getByText("0/3")).toBeVisible();
    expect(screen.getByText("0/10")).toBeVisible();
    expect(screen.getByRole("heading", { name: "No car retired" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "No classified car beat its call" })).toBeVisible();
    const retirements = screen.getByRole("heading", { name: "No car retired" }).closest("section")!;
    expect(within(retirements).getAllByRole("listitem")[0]).toHaveTextContent("STR");
    expect(within(retirements).getAllByRole("listitem")[1]).toHaveTextContent("—");
    expect(retirements).toHaveTextContent("0 cars were flagged; 0 of them retired");
  });

  it("falls back to the code for a car nobody can name", async () => {
    renderWithProviders(<ResultsReview review={REVIEW} predictions={[]} driverLookup={{}} year={2026} round={19} />);

    expect(await screen.findAllByText("VER")).not.toHaveLength(0);
  });

  it("reads a rolling-accuracy panel with no figures at all", () => {
    renderWithProviders(
      <ResultsReview
        review={{ evaluated: false }}
        accuracy={{ races_evaluated: 0 }}
        predictions={[]}
        driverLookup={{}}
        year={2026}
        round={19}
      />,
    );

    expect(screen.getByRole("heading", { name: "The last 0 scored races" })).toBeVisible();
    expect(screen.getAllByText("0%")).toHaveLength(3);
  });
});
