"use client";

import { useMemo } from "react";

import { getTeamColor, type DriverPrediction } from "@/app/components/PredictionDriverCard";

import { StatusPill } from "../components/RaceControlPrimitives";

import { ConsoleHeader, ConsolePanel, StatBlock } from "./predictionConsole";
import { deltaColor, deltaLabel, driverDisplayName, reviewBadgeLabel, reviewColor, shortName } from "./predictionHelpers";

import type {
  DriverLookup,
  PredictionDriverResult,
  PredictionReview,
  PredictionsResponse,
} from "./predictionModel";

/** Name and team for a driver code, from the snapshot first, standings second. */
interface DriverIdentity {
  name: string;
  team: string;
}

type IdentityLookup = Record<string, DriverIdentity>;

function buildIdentityLookup(predictions: DriverPrediction[], driverLookup: DriverLookup): IdentityLookup {
  const identities: IdentityLookup = {};
  for (const prediction of predictions) {
    identities[prediction.driver_code.toUpperCase()] = {
      name: driverDisplayName(prediction, driverLookup),
      team: prediction.team,
    };
  }
  // Drivers who raced but were not in the snapshot (a substitute, a late entry)
  // still need a name, so fall back to the championship table.
  for (const [code, standing] of Object.entries(driverLookup)) {
    identities[code] ??= { name: standing.name, team: standing.team };
  }
  return identities;
}

function identityFor(code: string, identities: IdentityLookup): DriverIdentity {
  return identities[code.toUpperCase()] ?? { name: code, team: "" };
}

/** getTeamColor matches on substrings, so an unknown team must not reach it. */
function teamColor(team: string): string {
  return team ? getTeamColor(team) : "#6B7280";
}

function positionLabel(position: number | null): string {
  return position == null ? "-" : `P${position}`;
}

/** Places gained against the call: positive means the driver beat the prediction. */
function placesBeatenBy(row: PredictionDriverResult): number | null {
  return row.position_delta == null ? null : -row.position_delta;
}

function outcomeLabel(row: PredictionDriverResult): string {
  if (row.crash) return "crash";
  if (row.dnf) return "dnf";
  if (row.actual_position == null) return "did not race";
  if (row.predicted_position == null) return "not predicted";
  return row.status ?? "classified";
}

function outcomeColor(row: PredictionDriverResult): string {
  if (row.crash || row.dnf) return "text-[#FF4655]";
  return "text-[#6F7789]";
}

function DriverComparisonRow({ row, identities }: { row: PredictionDriverResult; identities: IdentityLookup }) {
  const identity = identityFor(row.driver_code, identities);
  const beatenBy = placesBeatenBy(row);

  return (
    <tr className="bg-[#0D111B] text-sm text-[#B7BDCA] transition-colors hover:bg-[#121825]">
      <td className="px-4 py-3 font-mono text-[#8E96A8]">{positionLabel(row.predicted_position)}</td>
      <td className="px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="h-5 w-[3px] rounded-full" style={{ background: teamColor(identity.team) }} />
          <span className="font-mono text-sm font-black uppercase tracking-[0.08em] text-white">
            {row.driver_code}
          </span>
          <span className="truncate text-[#AEB5C5]">{shortName(identity.name)}</span>
        </div>
      </td>
      <td
        className={`px-4 py-3 font-mono font-bold ${row.exact ? "text-[#00FF78]" : "text-white"}`}
      >
        {positionLabel(row.actual_position)}
      </td>
      <td className={`px-4 py-3 text-right font-mono font-bold ${deltaColor(beatenBy)}`}>
        {row.exact ? "exact" : deltaLabel(beatenBy)}
      </td>
      <td className={`px-4 py-3 text-right font-mono text-xs uppercase tracking-[0.14em] ${outcomeColor(row)}`}>
        {outcomeLabel(row)}
      </td>
    </tr>
  );
}

function DriverComparisonTable({
  rows,
  identities,
}: {
  rows: PredictionDriverResult[];
  identities: IdentityLookup;
}) {
  const within3 = rows.filter(
    (row) => row.position_delta != null && Math.abs(row.position_delta) <= 3,
  ).length;
  const exact = rows.filter((row) => row.exact).length;
  const compared = rows.filter((row) => row.position_delta != null).length;

  return (
    <ConsolePanel>
      <ConsoleHeader
        label="Predicted vs actual - every driver"
        right={
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            {exact} exact / {within3} within 3 / {compared} compared
          </span>
        }
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left">
          <thead className="bg-[#0F141E] font-mono text-[10px] uppercase tracking-[0.22em] text-[#6F7789]">
            <tr className="border-b border-[#1E2633]">
              <th className="w-24 px-4 py-3">Predicted</th>
              <th className="px-4 py-3">Driver</th>
              <th className="w-24 px-4 py-3">Actual</th>
              <th className="w-28 px-4 py-3 text-right">Vs call</th>
              <th className="w-36 px-4 py-3 text-right">Outcome</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1E2633]">
            {rows.map((row) => (
              <DriverComparisonRow key={row.driver_code} row={row} identities={identities} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-[#1E2633] px-4 py-3 font-mono text-[11px] text-[#6F7789]">
        Vs call is places against the prediction — <span className="text-[#00FF78]">green beat it</span>,{" "}
        <span className="text-[#FF4655]">red fell short</span>.
      </p>
    </ConsolePanel>
  );
}

function WinnerCallPanel({ review, identities }: { review: PredictionReview; identities: IdentityLookup }) {
  const predicted = review.predicted_winner;
  const actual = review.actual_winner;

  return (
    <div className="grid gap-4 border-b border-[#1E2633] p-4 sm:grid-cols-2">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-[#6F7789]">Predicted winner</p>
        <p className="mt-1 text-xl font-black text-white">
          {predicted ? identityFor(predicted, identities).name : "-"}
        </p>
        <p className="mt-1 font-mono text-xs text-[#6F7789]">{predicted ?? "no stored call"}</p>
      </div>
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-[#6F7789]">Actual winner</p>
        <p className={`mt-1 text-xl font-black ${review.winner_correct ? "text-[#00FF78]" : "text-[#FF4655]"}`}>
          {actual ? identityFor(actual, identities).name : "-"}
        </p>
        <p className="mt-1 font-mono text-xs text-[#6F7789]">{actual ?? "not recorded"}</p>
      </div>
    </div>
  );
}

function PostRaceReviewGrid({ review }: { review: PredictionReview }) {
  return (
    <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
      <StatBlock
        label="Top 3"
        value={`${review.top3_correct ?? 0}/${review.top3_possible ?? 3}`}
        detail="predicted podium overlap"
      />
      <StatBlock
        label="Top 10"
        value={`${review.top10_correct ?? 0}/${review.top10_possible ?? 10}`}
        detail="points finish overlap"
      />
      <StatBlock
        label="Exact"
        value={`${review.exact_position_hits ?? 0}/${review.drivers_compared ?? 0}`}
        detail="exact finishing positions"
      />
      <StatBlock label="Avg error" value={`${review.avg_position_error ?? 0}`} detail="positions per compared driver" />
      <StatBlock
        label="DNF calls"
        value={`${review.dnf_correct ?? 0}/${review.dnf_actual ?? 0}`}
        detail="captured actual retirements"
      />
      <StatBlock
        label="Crash calls"
        value={`${review.crash_correct ?? 0}/${review.crash_actual ?? 0}`}
        detail="captured accident outcomes"
      />
    </div>
  );
}

function RollingAccuracyGrid({ accuracy }: { accuracy?: PredictionsResponse["accuracy"] }) {
  const window = accuracy?.rolling_window ?? 8;
  const dnfCapture = accuracy?.dnf_capture_pct == null ? "n/a" : `${accuracy.dnf_capture_pct}%`;
  const crashCapture = accuracy?.crash_capture_pct == null ? "n/a" : `${accuracy.crash_capture_pct}%`;

  return (
    <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
      <StatBlock label="Winner" value={`${accuracy?.recent_winner_pct ?? 0}%`} detail={`latest ${window} scored max`} />
      <StatBlock label="Top 3" value={`${accuracy?.recent_top3_pct ?? 0}%`} detail={`latest ${window} scored max`} />
      <StatBlock label="Top 10" value={`${accuracy?.recent_top10_pct ?? 0}%`} detail={`latest ${window} scored max`} />
      <StatBlock label="Avg error" value={`${accuracy?.avg_position_error ?? 0}`} detail="positions per driver" />
      <StatBlock label="DNF capture" value={dnfCapture} detail="actual DNF capture" />
      <StatBlock label="Crash capture" value={crashCapture} detail="actual crash capture" />
    </div>
  );
}

export function ResultsReview({
  review,
  accuracy,
  predictions,
  driverLookup,
}: {
  review?: PredictionReview;
  accuracy?: PredictionsResponse["accuracy"];
  predictions: DriverPrediction[];
  driverLookup: DriverLookup;
}) {
  const identities = useMemo(
    () => buildIdentityLookup(predictions, driverLookup),
    [predictions, driverLookup],
  );
  const evaluated = Boolean(review?.evaluated);
  const rows = review?.driver_results ?? [];

  return (
    <div className="space-y-4">
      <ConsolePanel>
        <ConsoleHeader
          label={evaluated ? "Post-race review" : "Rolling accuracy"}
          right={
            <StatusPill color={reviewColor(Boolean(review?.winner_correct), evaluated)}>
              {reviewBadgeLabel(review, accuracy?.races_evaluated ?? 0)}
            </StatusPill>
          }
        />
        {evaluated && review ? (
          <>
            <WinnerCallPanel review={review} identities={identities} />
            <PostRaceReviewGrid review={review} />
          </>
        ) : (
          <>
            <p className="border-b border-[#1E2633] px-4 py-3 text-sm text-[#8E96A8]">
              {review?.reason ?? "This race has not been scored against a result yet."}
            </p>
            <RollingAccuracyGrid accuracy={accuracy} />
          </>
        )}
      </ConsolePanel>

      {evaluated && rows.length > 0 && <DriverComparisonTable rows={rows} identities={identities} />}
    </div>
  );
}
