export interface DeltaChipProps {
  /** Places gained: positive moved up the order, negative dropped back, zero held station. */
  delta: number;
  className?: string;
}

type Trend = "gain" | "loss" | "even";

/**
 * Gained places read in `--rc-gain`, lost places in red text, no change in a
 * neutral tone. Never the DRS or sector colours: those keep their F1 meaning.
 */
const TREND: Record<Trend, { sign: string; tone: string }> = {
  gain: { sign: "+", tone: "bg-rc-gain/14 text-rc-gain" },
  loss: { sign: "−", tone: "bg-rc-red-text/14 text-rc-red-text" },
  even: { sign: "", tone: "bg-rc-ink/8 text-rc-ink-2" },
};

function trendOf(delta: number): Trend {
  if (delta > 0) return "gain";
  if (delta < 0) return "loss";
  return "even";
}

/** The change in words, for a screen reader: the sign and colour alone carry no meaning there. */
function spoken(trend: Trend, places: number): string {
  if (trend === "even") return "no change";
  return `${trend === "gain" ? "gained" : "lost"} ${places} ${places === 1 ? "place" : "places"}`;
}

/**
 * Places gained or lost, as a small signed chip: "+3", "−2", "0".
 *
 * Renders nothing for a value that is not a number, since a made-up zero
 * would read as "held position". A retirement or a pit-lane start is the
 * caller's to label.
 */
export function DeltaChip({ delta, className = "" }: DeltaChipProps) {
  if (!Number.isFinite(delta)) return null;
  const trend = trendOf(delta);
  const places = Math.abs(delta);
  return (
    <span
      data-trend={trend}
      className={`inline-flex items-center rounded-sm px-[5px] py-[3px] font-mono text-[11px] font-semibold leading-none tabular-nums ${TREND[trend].tone} ${className}`}
    >
      <span aria-hidden="true">
        {TREND[trend].sign}
        {places}
      </span>
      <span className="sr-only">{spoken(trend, places)}</span>
    </span>
  );
}
