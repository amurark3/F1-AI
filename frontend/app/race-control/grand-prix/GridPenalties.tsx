"use client";

import { Gavel } from "lucide-react";

import { getTeamColor } from "@/app/lib/teamColors";

import { netMoveColor, netMoveLabel, penaltyLabel, qualifiedLabel, startLabel } from "./gridHelpers";
import { ConsoleHeader, ConsolePanel } from "./predictionConsole";
import { shortName } from "./predictionHelpers";

import type { StartingGridResponse } from "./gridModel";

/** Header cell shared by the penalties table. */
function Th({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return <th className={align === "right" ? "px-4 py-3 text-right" : "px-4 py-3 text-left"}>{children}</th>;
}

/**
 * Every sanction applied to this round's grid.
 *
 * Deliberately has no "reason" column. The published grid sheet records how
 * many places a driver dropped, not the offence behind it, and there is no
 * source in this stack for the latter — a plausible-looking "gearbox change"
 * would be invented, not reported.
 */
/**
 * What the empty state may claim, which depends entirely on what is known.
 *
 * "No penalties were applied" is a statement of fact about a published grid
 * sheet. Saying it for a round whose qualifying has not run — or whose sheet
 * has not been released — asserts something nobody has checked.
 */
function emptyStateMessage(data?: StartingGridResponse): string {
  if (!data?.available) {
    return "Penalties are not known for this round yet. They are published with the starting grid, once qualifying has run.";
  }
  if (data.provisional) {
    return "Penalties cannot be listed yet — the official grid sheet for this round has not been published, so only the qualifying order is known.";
  }
  return "No grid penalties were applied for this round. Every driver starts from the slot they qualified in.";
}

export function GridPenalties({ data }: { data?: StartingGridResponse }) {
  const penalties = data?.penalties ?? [];

  return (
    <ConsolePanel>
      <ConsoleHeader
        label="Grid penalties"
        right={
          <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            <Gavel className="h-3.5 w-3.5 text-[#F5C542]" />
            {data?.available ? `${penalties.length} applied` : "not known yet"}
          </span>
        }
      />

      {penalties.length === 0 ? (
        <p className="p-4 text-sm leading-relaxed text-[#8E96A8]">{emptyStateMessage(data)}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] border-collapse text-left">
            <thead className="bg-[#0F141E] font-mono text-[10px] uppercase tracking-[0.22em] text-[#6F7789]">
              <tr className="border-b border-[#1E2633]">
                <Th>Driver</Th>
                <Th>Team</Th>
                <Th align="right">Qualified</Th>
                <Th align="right">Penalty</Th>
                <Th align="right">Starts</Th>
                <Th align="right">Net</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1E2633]">
              {penalties.map((slot) => (
                <tr key={slot.driver_code} className="bg-[#0D111B] text-sm text-[#B7BDCA] hover:bg-[#121825]">
                  <td className="px-4 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="h-5 w-[3px] rounded-full" style={{ background: getTeamColor(slot.team) }} />
                      <span className="font-mono text-sm font-black uppercase tracking-[0.08em] text-white">
                        {slot.driver_code}
                      </span>
                      <span className="truncate text-[#AEB5C5]">{shortName(slot.driver_name)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-[#AEB5C5]">{slot.team || "-"}</td>
                  <td className="px-4 py-3 text-right font-mono text-[#8E96A8]">{qualifiedLabel(slot)}</td>
                  <td className="px-4 py-3 text-right font-mono text-[#F5C542]">{penaltyLabel(slot)}</td>
                  <td className="px-4 py-3 text-right font-mono font-bold text-white">{startLabel(slot)}</td>
                  <td className={`px-4 py-3 text-right font-mono font-bold ${netMoveColor(slot)}`}>
                    {netMoveLabel(slot)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {penalties.length > 0 && (
        <p className="border-t border-[#1E2633] px-4 py-3 text-xs leading-relaxed text-[#596173]">
          &ldquo;Net&rdquo; is the slots actually dropped between qualifying and the grid, which is smaller than the
          penalty whenever a driver ahead is also penalised. The offence behind each penalty is not published in
          this data source and is not shown.
        </p>
      )}
    </ConsolePanel>
  );
}
