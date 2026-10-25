/**
 * A car's use of one element as a row of pips: one per allowed unit — filled in
 * the team colour once used, hollow while still in hand — then a hairline at the
 * allowance and one red pip per unit beyond it.
 *
 * Server-safe: no state, no effects.
 */
import { OVER_COLOR, type ElementUsage } from "./powerUnitsModel";

function Pip({ filled, color }: { filled: boolean; color: string }) {
  return (
    <span
      className="h-3 w-[7px] rounded-[2px] border"
      style={{ background: filled ? color : "transparent", borderColor: filled ? color : "#2C3646" }}
    />
  );
}

export function ElementPips({ usage, teamColor }: { usage: ElementUsage; teamColor: string }) {
  const allowance = usage.allowance ?? usage.used;
  const withinUsed = Math.min(usage.used, allowance);
  const label = `${usage.code}: ${usage.used} used of ${usage.allowance ?? "unknown"} allowed${
    usage.over_by ? `, ${usage.over_by} beyond the allowance` : ""
  }`;

  return (
    <span className="inline-flex items-center gap-[3px]" role="img" aria-label={label} title={label}>
      {Array.from({ length: allowance }, (_, index) => (
        <Pip key={`a${index}`} filled={index < withinUsed} color={teamColor} />
      ))}
      {usage.over_by > 0 && (
        <>
          <span className="mx-[2px] h-4 w-px bg-[#5A6273]" aria-hidden="true" />
          {Array.from({ length: usage.over_by }, (_, index) => (
            <Pip key={`o${index}`} filled color={OVER_COLOR} />
          ))}
        </>
      )}
    </span>
  );
}

/** "7/4" with the overrun called out, for tight spaces. */
export function UsageCount({ usage }: { usage: ElementUsage }) {
  const over = usage.over_by > 0;
  return (
    <span className="font-mono text-[11px] font-bold tabular-nums" style={{ color: over ? OVER_COLOR : "#B7BDCA" }}>
      {usage.used}
      <span className="text-[#5A6273]">/{usage.allowance ?? "?"}</span>
    </span>
  );
}
