"use client";

import { Flag } from "lucide-react";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";
import { DriverLink } from "../profiles/EntityLinks";

import {
  buildGridLayout,
  gridNote,
  gridTitle,
  lastSlot,
  penaltyNote,
  promotedNote,
  qualifiedNote,
  reasonNote,
  type GridRow,
} from "./gridHelpers";
import { FinalTag, StateTag } from "./StateTag";

import type { GridSlot, StartingGridResponse } from "./gridModel";

const NO_DSQ: ReadonlySet<string> = new Set();

interface GridContext {
  slots: GridSlot[];
  last: number;
  dsq: ReadonlySet<string>;
}

/** One car: the slot, the driver, and only the facts that explain why it is there. */
function GridBox({ slot, context }: { slot: GridSlot; context: GridContext }) {
  const qualified = qualifiedNote(slot, context.dsq);
  const penalty = penaltyNote(slot, context.last);
  const promoted = promotedNote(slot, context.slots);
  const reason = reasonNote(slot);

  return (
    <div
      className="flex min-w-0 items-start gap-3 rounded-sm border border-rc-line bg-(--surface) py-2.5 pr-3 pl-3"
      style={{ borderLeft: `3px solid ${getTeamColor(slot.team)}` }}
    >
      <span className="w-7 shrink-0 text-center font-mono text-lg leading-none font-semibold text-rc-ink">
        {slot.position ?? "—"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] leading-tight font-semibold text-rc-ink">
          <DriverLink code={slot.driver_code} name={slot.driver_name}>
            <DriverName variant="full" code={slot.driver_code} name={slot.driver_name} />
          </DriverLink>{" "}
          <span className="font-mono text-[11px] text-rc-ink-3">{slot.driver_code}</span>
        </p>
        {qualified && <p className="mt-1 font-mono text-[11px] text-rc-ink-3">{qualified}</p>}
        {penalty && (
          <p className="mt-1">
            <StateTag tone="red">{penalty}</StateTag>
          </p>
        )}
        {reason && <p className="mt-1 text-[11px] leading-snug text-rc-ink-3">{reason}</p>}
        {promoted && (
          <p className="mt-1 font-mono text-[11px] text-rc-gain">
            +{promoted.places}
            {promoted.by.length > 0 && ` promoted by ${promoted.by.map((code) => `${code}’s drop`).join(", ")}`}
          </p>
        )}
      </div>
    </div>
  );
}

function EmptyBox() {
  return <div className="rounded-sm border border-dashed border-rc-line-soft" />;
}

/** The odd slot leads, the even slot sits back from it, as on track. */
function GridRowPair({ row, context }: { row: GridRow; context: GridContext }) {
  return (
    <div className="grid grid-cols-2 gap-x-3 sm:gap-x-8">
      <div className="min-w-0">{row.leading ? <GridBox slot={row.leading} context={context} /> : <EmptyBox />}</div>
      <div className="min-w-0 translate-y-5">
        {row.trailing ? <GridBox slot={row.trailing} context={context} /> : <EmptyBox />}
      </div>
    </div>
  );
}

/** Pit-lane starters hold no slot: they sit in their own box, never in a numbered place. */
function PitLaneBox({ slots, context }: { slots: GridSlot[]; context: GridContext }) {
  if (slots.length === 0) return null;
  return (
    <div className="mt-10 border-t border-dashed border-rc-line pt-4">
      <p className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-rc-red-text">Pit lane</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {slots.map((slot) => (
          <GridBox key={slot.driver_code} slot={slot} context={context} />
        ))}
      </div>
    </div>
  );
}

function StartLine() {
  return (
    <div className="mb-6">
      <div className="h-px w-full bg-rc-ink-3" />
      <p className="mt-2 text-center font-mono text-[10px] font-semibold uppercase tracking-[0.3em] text-rc-ink-3">
        Start / Finish
      </p>
    </div>
  );
}

function NoGridPanel({ reason }: { reason: string }) {
  return (
    <div className="flex items-start gap-4 p-5">
      <Flag className="mt-0.5 h-5 w-5 shrink-0 text-rc-ink-3" aria-hidden />
      <div>
        <p className="text-sm font-semibold text-rc-ink">The grid is not set yet</p>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-rc-ink-3">{reason}</p>
      </div>
    </div>
  );
}

export interface StartingGridProps {
  data?: StartingGridResponse;
  raceName: string;
  /** Codes disqualified from qualifying, so their row says `DSQ` where it would say where they qualified. */
  dsqCodes?: ReadonlySet<string>;
}

/**
 * The starting grid, staggered the way Formula 1 draws it. A car is drawn in the slot it
 * started from, with the sanction behind it; a car that started where it qualified carries
 * nothing extra.
 */
export function StartingGrid({ data, raceName, dsqCodes = NO_DSQ }: StartingGridProps) {
  const slots = data?.grid ?? [];
  const layout = buildGridLayout(slots);
  const context: GridContext = { slots, last: lastSlot(slots), dsq: dsqCodes };

  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow={`Starting grid · ${raceName}`}
        title={gridTitle(data)}
        sub="as the cars lined up · a car that started where it qualified shows only its slot"
        aside={data?.available ? <FinalTag final={!data.provisional} /> : undefined}
      />

      {layout.rows.length === 0 && layout.pitLane.length === 0 ? (
        <NoGridPanel
          reason={data?.warnings?.[0] ?? "The starting order appears here once qualifying has run for this Grand Prix."}
        />
      ) : (
        <div className="mx-auto max-w-[620px] min-w-[300px]">
          <StartLine />
          <div className="space-y-5">
            {layout.rows.map((row) => (
              <GridRowPair key={row.row} row={row} context={context} />
            ))}
          </div>
          <PitLaneBox slots={layout.pitLane} context={context} />
        </div>
      )}
      <p className="mt-6 font-mono text-[10px] leading-relaxed tracking-[0.04em] text-rc-ink-3">{gridNote(data)}</p>
    </Panel>
  );
}
