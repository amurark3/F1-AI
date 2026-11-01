/**
 * One finish as a compact, colour-coded label: gold for a win, silver for a
 * podium, green for points, red for a retirement. The grid slot, places
 * gained and retirement reason sit in the tooltip.
 *
 * Server-safe: no state, no effects.
 */
import { finishColor, finishDetail, finishLabel, type Finish } from "./profilesModel";

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
