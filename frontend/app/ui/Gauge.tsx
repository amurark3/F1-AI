import { GAUGE_PATH_LENGTH, gaugeDashOffset, gaugeReading, shareText } from "./gaugeArc";
import { f1, rc } from "./tokens";

export interface GaugeProps {
  /** The reading; `null` when there is none. */
  value: number | null;
  /** What the value is, shown under the ring and used as its accessible name: "Winner right". */
  label: string;
  /** The ring's empty end. */
  min?: number;
  /** The ring's full end. */
  max?: number;
  /** The figure written in the ring; the value's share of the range ("62%") when left out. */
  valueText?: string;
  /** The arc's colour: the brand red fill, or a team colour on an entity page. */
  color?: string;
  className?: string;
}

/** The ring, in viewBox units (gp-predictions.html's scorecard). */
const CENTRE = 40;
const RADIUS = 32;
const STROKE = 7;
const VALUE_BASELINE = 46;

/**
 * One value against its range as a ring (the mockups' model scorecard): a
 * hairline track, an arc filled from the top by the value's share, the figure
 * inside and the label under it. The figure and label are always written out,
 * so nothing rests on the arc or its colour.
 *
 * A screen reader meets a `meter` with the range and the figure as its value
 * text. A missing value shows a dash and is named "no data", since an empty
 * ring would read as a real zero. The arc fills in once on arrival behind
 * `motion-safe`.
 */
export function Gauge({ value, label, min = 0, max = 100, valueText, color = f1.red, className = "" }: GaugeProps) {
  const reading = gaugeReading(value, min, max);
  const figure = reading === null ? "—" : (valueText ?? shareText(reading.share));
  const a11y =
    reading === null
      ? { role: "img", "aria-label": `${label}: no data` }
      : {
          role: "meter",
          "aria-label": label,
          "aria-valuemin": min,
          "aria-valuemax": max,
          "aria-valuenow": reading.now,
          "aria-valuetext": figure,
        };

  return (
    <div {...a11y} className={`text-center ${className}`}>
      <svg viewBox={`0 0 ${2 * CENTRE} ${2 * CENTRE}`} aria-hidden="true" className="mx-auto block w-[92px]">
        <circle cx={CENTRE} cy={CENTRE} r={RADIUS} fill="none" stroke={rc.line} strokeWidth={STROKE} />
        {reading !== null && reading.fill > 0 && (
          <circle
            data-arc
            cx={CENTRE}
            cy={CENTRE}
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth={STROKE}
            strokeLinecap="round"
            pathLength={GAUGE_PATH_LENGTH}
            strokeDasharray={`${GAUGE_PATH_LENGTH} ${GAUGE_PATH_LENGTH}`}
            strokeDashoffset={gaugeDashOffset(reading.fill)}
            transform={`rotate(-90 ${CENTRE} ${CENTRE})`}
            className="motion-safe:animate-gauge-fill"
          />
        )}
        <text
          x={CENTRE}
          y={VALUE_BASELINE}
          textAnchor="middle"
          className="fill-rc-ink font-display text-[22px] font-extrabold"
        >
          {figure}
        </text>
      </svg>
      <p className="mt-1.5 font-mono text-[10px] font-medium uppercase leading-[1.3] tracking-[0.1em] text-rc-ink-3">
        {label}
      </p>
    </div>
  );
}
