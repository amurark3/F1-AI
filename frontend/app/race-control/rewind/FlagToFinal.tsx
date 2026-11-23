"use client";

import { DeltaChip } from "@/app/ui/DeltaChip";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { FinalTag } from "../grand-prix/StateTag";

import { finalTitle, penaltyText } from "./rewindCopy";

import type { RaceRewind, RewindFinalRow } from "./rewindTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";

function Row({ row }: { row: RewindFinalRow }) {
  const delta = row.road_position !== null && row.position !== null ? row.road_position - row.position : 0;
  return (
    <li className="grid grid-cols-[22px_38px_minmax(0,1fr)_auto_auto] items-center gap-2 border-b border-rc-line-soft py-[5px] text-xs">
      <span className="text-right font-mono text-[11px] text-rc-ink-3">{row.position}</span>
      <b className="font-mono text-xs font-semibold text-rc-ink">{row.driver_code}</b>
      <span className="text-rc-ink-2">{row.road_position === null ? "" : `road P${row.road_position}`}</span>
      {delta === 0 ? <span /> : <DeltaChip delta={delta} />}
      <span className="text-xs text-rc-ink-3">{row.penalties.map(penaltyText).join(" · ")}</span>
    </li>
  );
}

/** The road order at the flag against the classification. */
export function FlagToFinal({ data }: { data: RaceRewind }) {
  const { final } = data;
  if (!final) {
    return (
      <div className={CARD}>
        <PanelHeading eyebrow="At the flag → classified" title="Not classified yet" />
        <p className="text-sm text-rc-ink-3">
          The classification isn&apos;t published yet; the Final step appears when it is.
        </p>
      </div>
    );
  }
  return (
    <figure className={CARD}>
      <PanelHeading
        eyebrow="At the flag → classified"
        title={finalTitle(final)}
        sub={`Road order at the line on lap ${data.total_laps} against the ${final.provisional ? "provisional classification" : "FIA final classification"}`}
        aside={<FinalTag final={!final.provisional} />}
      />
      <ol>
        {final.rows
          .filter((row) => row.position !== null)
          .map((row) => (
            <Row key={row.driver_code} row={row} />
          ))}
      </ol>
    </figure>
  );
}
