/**
 * One finish as a compact, colour-coded label: gold for a win, silver for a
 * podium, green for points, red for a retirement. The grid slot, places
 * gained and retirement reason sit in the tooltip.
 *
 * The label, colour and tooltip rules live here with their only user: the
 * Team and Driver pages' results grids, which P5.4 rebuilds per the mockups.
 *
 * Server-safe: no state, no effects.
 */
import { formatPoints, type Finish } from "./profilesModel";

const PODIUM_POSITIONS = 3;
const WIN_COLOR = "#FFD15C";
const PODIUM_COLOR = "#E8E8E8";
const POINTS_COLOR = "#00FF78";
const RETIRED_COLOR = "#FF6B6B";
const MUTED_COLOR = "#5A6273";

/** "P3", "DNF", "DNS" — or an em dash for a round the car did not take part in. */
function finishLabel(finish: Finish | null): string {
  if (!finish) return "—";
  return finish.position === null ? finish.position_text || "NC" : `P${finish.position}`;
}

/** The colour a finish reads in: gold for a win, through to muted for no points. */
function finishColor(finish: Finish | null): string {
  if (!finish) return MUTED_COLOR;
  if (finish.position === null) return RETIRED_COLOR;
  if (finish.position === 1) return WIN_COLOR;
  if (finish.position <= PODIUM_POSITIONS) return PODIUM_COLOR;
  return finish.points > 0 ? POINTS_COLOR : "#B7BDCA";
}

/** Tooltip text for a finish: the grid slot, places gained, and why it ended. */
function finishDetail(finish: Finish | null): string {
  if (!finish) return "Did not take part";
  const parts = [finish.grid ? `Started P${finish.grid}` : "No grid slot"];
  if (finish.positions_gained) {
    parts.push(`${finish.positions_gained > 0 ? "+" : ""}${finish.positions_gained} places`);
  }
  parts.push(`${formatPoints(finish.points)} pts`);
  if (finish.reason_retired) parts.push(finish.reason_retired);
  if (finish.pole) parts.push("Pole");
  if (finish.fastest_lap) parts.push("Fastest lap");
  return parts.join(" · ");
}

export function FinishChip({ finish, size = "md" }: { finish: Finish | null; size?: "sm" | "md" }) {
  const color = finishColor(finish);
  const detail = finishDetail(finish);
  const sizing = size === "sm" ? "min-w-8 px-1 text-[10px]" : "min-w-10 px-1.5 text-xs";
  return (
    <span
      className={`inline-flex items-center justify-center rounded border py-0.5 font-mono font-black tabular-nums ${sizing}`}
      style={{ color, borderColor: `${color}40`, background: finish ? `${color}12` : "transparent" }}
      title={detail}
      aria-label={`${finishLabel(finish)}: ${detail}`}
    >
      {finishLabel(finish)}
    </span>
  );
}
