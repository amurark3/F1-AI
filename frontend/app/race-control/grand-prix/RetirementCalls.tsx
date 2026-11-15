"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";

import { DNF_FLAG_PCT, retirementTitle, type OutRow } from "./reviewModel";

import type { IdentityLookup } from "./CallChart";
import type { PredictionReview } from "./predictionModel";

function RetirementLine({ row, identities }: { row: OutRow; identities: IdentityLookup }) {
  const identity = identities[row.code] ?? { name: row.code, team: "" };
  return (
    <li className="flex items-center gap-3 border-b border-rc-line-soft py-2.5">
      <span className="h-3.5 w-[3px] shrink-0 rounded-full" style={{ background: getTeamColor(identity.team) }} />
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] font-semibold text-rc-ink">
          <DriverName variant="codeLast" code={row.code} name={identity.name} />
        </span>
        <span className="block text-[11px] text-rc-ink-3">{row.detail}</span>
      </span>
      <span className="font-mono text-xs font-semibold text-rc-ink-2">{row.risk === null ? "—" : `${row.risk}%`}</span>
      <span className={`w-20 text-right font-mono text-xs ${row.flagged ? "text-rc-ink" : "text-rc-ink-3"}`}>
        {row.flagged ? "flagged" : "not flagged"}
      </span>
    </li>
  );
}

/** Retirements the risk model flagged out of all retirements, and the cars it flagged in total. */
export function RetirementCalls({
  review,
  retired,
  identities,
}: {
  review: PredictionReview;
  retired: OutRow[];
  identities: IdentityLookup;
}) {
  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow="Retirement calls"
        title={retirementTitle(review)}
        sub={`Retirement risk before the race · flagged = ${DNF_FLAG_PCT}% or more, the threshold the score uses`}
      />
      <ul>
        {retired.map((row) => (
          <RetirementLine key={row.code} row={row} identities={identities} />
        ))}
      </ul>
      <p className="mt-4 font-mono text-[10px] leading-relaxed tracking-[0.04em] text-rc-ink-3">
        {review.dnf_predicted ?? 0} cars were flagged; {review.dnf_correct ?? 0} of them retired · incidents (collision,
        accident) against mechanical come from the classification&apos;s reasons: crash risk caught{" "}
        {review.crash_correct ?? 0} of {review.crash_actual ?? 0} incidents
      </p>
    </Panel>
  );
}
