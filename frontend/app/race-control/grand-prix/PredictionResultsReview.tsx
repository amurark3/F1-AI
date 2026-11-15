"use client";

import Link from "next/link";
import { useMemo } from "react";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { grandPrixHref } from "@/app/lib/entityLinks";
import { driverLabel } from "@/app/ui/names/names";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { StatTile, StatTiles } from "@/app/ui/StatTile";
import { fetcher } from "@/app/utils/fetcher";

import { Panel } from "../components/RaceControlPrimitives";
import { useSeasonDirectory } from "../profiles/EntityLinks";

import { CallChart, type IdentityLookup } from "./CallChart";
import { driverDisplayName } from "./predictionHelpers";
import { RetirementCalls } from "./RetirementCalls";
import { buildReviewRows, retiredRows, withinThree, winnerSub } from "./reviewModel";
import { FinalTag } from "./StateTag";

import type { DriverLookup, DriverPrediction, PredictionReview, PredictionsResponse } from "./predictionModel";
import type { RaceResultsResponse } from "./resultsModel";

const REFRESH = { revalidateOnFocus: false, dedupingInterval: 120_000 };

/** Name and team for a driver code, from the snapshot first, standings second. */
function buildIdentities(predictions: DriverPrediction[], driverLookup: DriverLookup): IdentityLookup {
  const identities: IdentityLookup = {};
  for (const prediction of predictions) {
    identities[prediction.driver_code.toUpperCase()] = {
      name: driverDisplayName(prediction, driverLookup),
      team: prediction.team,
    };
  }
  // A substitute or late entry is not in the snapshot but still needs a name.
  for (const [code, standing] of Object.entries(driverLookup)) {
    identities[code] ??= { name: standing.name, team: standing.team };
  }
  return identities;
}

function ScoreStrip({
  review,
  within,
  nameOf,
}: {
  review: PredictionReview;
  within: number;
  nameOf: (code: string) => string;
}) {
  return (
    <StatTiles>
      <StatTile
        label="Winner"
        value={
          <span className={review.winner_correct ? "text-rc-gold" : undefined}>
            {review.winner_correct ? "Right" : "Missed"}
          </span>
        }
        sub={winnerSub(review, nameOf)}
      />
      <StatTile
        label="Podium"
        value={`${review.top3_correct ?? 0}/${review.top3_possible ?? 3}`}
        sub="called podium cars that made it"
      />
      <StatTile
        label="Top ten"
        value={`${review.top10_correct ?? 0}/${review.top10_possible ?? 10}`}
        sub="called points finishers that scored"
      />
      <StatTile
        label="Average miss"
        value={review.avg_position_error ?? 0}
        unit="places"
        sub={`over ${review.drivers_compared ?? 0} classified cars · ${review.exact_position_hits ?? 0} exact · ${within} within 3`}
      />
    </StatTiles>
  );
}

function RollingAccuracy({ accuracy, reason }: { accuracy?: PredictionsResponse["accuracy"]; reason?: string }) {
  const window = accuracy?.rolling_window ?? 8;
  const capture = (value?: number | null) => (value == null ? "n/a" : `${value}%`);
  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow="Rolling accuracy"
        title={`The last ${accuracy?.races_evaluated ?? 0} scored races`}
        sub={reason ?? "This race has not been scored against a result yet."}
      />
      <StatTiles>
        <StatTile label="Winner" value={`${accuracy?.recent_winner_pct ?? 0}%`} sub={`latest ${window} scored max`} />
        <StatTile label="Podium" value={`${accuracy?.recent_top3_pct ?? 0}%`} sub="places right" />
        <StatTile label="Top ten" value={`${accuracy?.recent_top10_pct ?? 0}%`} sub="places right" />
        <StatTile
          label="Average miss"
          value={accuracy?.avg_position_error ?? 0}
          unit="places"
          sub="classified cars only"
        />
        <StatTile label="Retirements" value={capture(accuracy?.dnf_capture_pct)} sub="flagged beforehand" />
      </StatTiles>
    </Panel>
  );
}

function ScoredReview({
  review,
  identities,
  results,
  round,
}: {
  review: PredictionReview;
  identities: IdentityLookup;
  results: RaceResultsResponse | undefined;
  round: number;
}) {
  const rows = useMemo(() => buildReviewRows(review, results), [review, results]);
  const directory = useSeasonDirectory();
  const nameOf = (code: string) => identities[code.toUpperCase()]?.name ?? code;
  const surnameOf = (code: string) => driverLabel({ name: nameOf(code), code }, "last", directory);
  const final = review.actual_provisional === false;

  return (
    <div className="space-y-4">
      <Panel as="section" className="p-5">
        <PanelHeading
          eyebrow="Scored against Results"
          sub={
            final
              ? "The final classification"
              : "Scored against the provisional result; it is scored again when the final lands"
          }
          aside={<FinalTag final={final} />}
        />
        <ScoreStrip review={review} within={withinThree(rows)} nameOf={nameOf} />
      </Panel>
      <div className="grid items-start gap-4 lg:grid-cols-[3fr_1fr]">
        <CallChart rows={rows} identities={identities} surnameOf={surnameOf} />
        <div className="space-y-4">
          <RetirementCalls review={review} retired={retiredRows(rows)} identities={identities} />
          <Panel as="section" className="p-5">
            <PanelHeading eyebrow="How a call is scored" />
            <p className="text-[13px] text-rc-ink-2">
              A classified car scores the places between its call and its result. A retirement reads DNF with its reason
              and no number: it counts only as a retirement call, never in the average miss.
            </p>
            <Link
              href={grandPrixHref(round, "results")}
              className="mt-3 inline-block font-mono text-xs text-rc-blue hover:text-rc-ink"
            >
              Final classification
            </Link>
          </Panel>
        </div>
      </div>
    </div>
  );
}

/**
 * The Review view: the stored call scored against Results. It prints no
 * results table; a retirement's reason is read from the classification.
 */
export function ResultsReview({
  review,
  accuracy,
  predictions,
  driverLookup,
  year,
  round,
}: {
  review?: PredictionReview;
  accuracy?: PredictionsResponse["accuracy"];
  predictions: DriverPrediction[];
  driverLookup: DriverLookup;
  year: number;
  round: number | null;
}) {
  const identities = useMemo(() => buildIdentities(predictions, driverLookup), [predictions, driverLookup]);
  const scored = Boolean(review?.evaluated);
  // Held back until a review exists: an unscored race has no retirement to explain.
  const results = useSWR<RaceResultsResponse, Error>(
    scored && round !== null ? `${API_BASE}/api/race-control/results/${year}/${round}` : null,
    fetcher,
    REFRESH,
  );

  if (!scored || !review || round === null) {
    return <RollingAccuracy accuracy={accuracy} reason={review?.reason} />;
  }
  return <ScoredReview review={review} identities={identities} results={results.data} round={round} />;
}
