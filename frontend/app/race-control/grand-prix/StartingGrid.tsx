"use client";

import { AlertTriangle, Flag } from "lucide-react";
import { useMemo } from "react";

import { getTeamColor } from "@/app/lib/teamColors";

import { buildGridLayout, gridSourceLabel, penaltyChipLabel, type GridRow } from "./gridHelpers";
import { ConsoleHeader, ConsolePanel } from "./predictionConsole";
import { shortName } from "./predictionHelpers";

import type { GridSlot, StartingGridResponse } from "./gridModel";

/**
 * One grid box: the slot number, the driver, and any sanction that put them
 * there.
 *
 * The team colour runs down the leading edge the way it does on a broadcast
 * grid graphic, so the row reads as a line-up rather than as a table.
 */
function GridBox({ slot }: { slot: GridSlot }) {
  const color = getTeamColor(slot.team);
  const penalty = penaltyChipLabel(slot);

  return (
    <div
      className="relative flex min-w-0 items-center gap-3 overflow-hidden rounded-sm border border-[#1E2633] bg-[#111724] py-2.5 pl-3 pr-3"
      style={{ borderLeft: `3px solid ${color}` }}
    >
      <span className="w-7 shrink-0 text-center font-mono text-lg font-black leading-none text-white">
        {slot.position}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-[13px] font-black uppercase tracking-[0.1em] text-white">
          {slot.driver_code}
        </p>
        <p className="truncate text-[11px] leading-tight text-[#8E96A8]">{shortName(slot.driver_name)}</p>
        <p className="truncate text-[10px] leading-tight text-[#596173]">{slot.team || "-"}</p>
      </div>
      {penalty && (
        <span className="shrink-0 self-start rounded border border-[#F5C542]/40 bg-[#F5C542]/10 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-[#F5C542]">
          {penalty}
        </span>
      )}
    </div>
  );
}

/** An unfilled half-row, drawn so the stagger keeps its shape at the back. */
function EmptyBox() {
  return <div className="rounded-sm border border-dashed border-[#1A212D]" />;
}

/**
 * One staggered row: the odd slot leads, the even slot sits back from it.
 *
 * The offset is what makes the drawing a grid rather than a two-column table —
 * on track the even side really does start roughly half a car-length behind.
 */
function GridRowPair({ row }: { row: GridRow }) {
  return (
    <div className="grid grid-cols-2 gap-x-3 sm:gap-x-8">
      <div className="min-w-0">{row.leading ? <GridBox slot={row.leading} /> : <EmptyBox />}</div>
      <div className="min-w-0 translate-y-5">{row.trailing ? <GridBox slot={row.trailing} /> : <EmptyBox />}</div>
    </div>
  );
}

/** Drivers released from the pit lane, who start behind the grid entirely. */
function PitLaneRow({ slots }: { slots: GridSlot[] }) {
  if (slots.length === 0) return null;

  return (
    <div className="mt-10 border-t border-dashed border-[#2A3342] pt-4">
      <p className="mb-2 font-mono text-[10px] font-black uppercase tracking-[0.24em] text-[#F5C542]">
        Pit lane start
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {slots.map((slot) => (
          <GridBox key={slot.driver_code} slot={slot} />
        ))}
      </div>
    </div>
  );
}

/** The start/finish line the front row lines up behind. */
function StartLine() {
  return (
    <div className="mb-6">
      <div
        className="h-3 w-full rounded-sm"
        style={{
          backgroundImage:
            "repeating-linear-gradient(90deg, #E7E9EE 0 10px, #10141D 10px 20px), repeating-linear-gradient(90deg, #10141D 0 10px, #E7E9EE 10px 20px)",
          backgroundSize: "100% 50%",
          backgroundPosition: "0 0, 0 100%",
          backgroundRepeat: "no-repeat",
        }}
      />
      <p className="mt-2 text-center font-mono text-[10px] font-black uppercase tracking-[0.3em] text-[#6F7789]">
        Start / Finish
      </p>
    </div>
  );
}

/** Shown when qualifying has not run, so no grid exists to draw. */
function NoGridPanel({ reason }: { reason: string }) {
  return (
    <div className="flex items-start gap-4 p-6">
      <Flag className="mt-0.5 h-5 w-5 shrink-0 text-[#596173]" />
      <div>
        <p className="text-sm font-bold text-white">The grid is not set yet</p>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[#8E96A8]">{reason}</p>
      </div>
    </div>
  );
}

/** The provisional banner, shown only when the order is not the grid sheet. */
function ProvisionalNotice({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 border-b border-[#1E2633] bg-[#F5C542]/[0.06] px-4 py-3">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#F5C542]" />
      <p className="text-sm leading-relaxed text-[#D7C69A]">{message}</p>
    </div>
  );
}

export interface StartingGridProps {
  data?: StartingGridResponse;
  raceName: string;
}

/**
 * The starting grid, drawn the way Formula 1 draws it.
 *
 * Positions stagger left and right from the start line rather than listing in
 * a single column, and a penalised driver is shown in the slot they actually
 * start from, with the sanction that put them there attached.
 */
export function StartingGrid({ data, raceName }: StartingGridProps) {
  const layout = useMemo(() => buildGridLayout(data?.grid ?? []), [data?.grid]);
  const provisionalWarning = data?.provisional ? data.warnings?.[0] : undefined;

  return (
    <ConsolePanel>
      <ConsoleHeader
        label={`Starting grid - ${raceName}`}
        right={
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            {gridSourceLabel(data?.source ?? "unavailable")}
          </span>
        }
      />

      {provisionalWarning && <ProvisionalNotice message={provisionalWarning} />}

      {layout.rows.length === 0 && layout.pitLane.length === 0 ? (
        <NoGridPanel
          reason={
            data?.warnings?.[0] ??
            "The starting order appears here once qualifying has run for this Grand Prix."
          }
        />
      ) : (
        <div className="overflow-x-auto p-4 sm:p-6">
          <div className="mx-auto min-w-[300px] max-w-[560px]">
            <StartLine />
            <div className="space-y-5">
              {layout.rows.map((row) => (
                <GridRowPair key={row.row} row={row} />
              ))}
            </div>
            <PitLaneRow slots={layout.pitLane} />
          </div>
        </div>
      )}
    </ConsolePanel>
  );
}
