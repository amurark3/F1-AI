import {
  deltaText,
  SLOPE,
  slopeDelta,
  slopeLayout,
  slopeValueText,
  spokenChange,
  trendOf,
  type SlopeRow,
  type SlopeScale,
  type SlopeTrend,
} from "./slopeLayout";
import { rc } from "./tokens";

export interface SlopeItem {
  /** Unique within the chart. */
  id: string;
  /** The short name at both ends: the driver code, as on every chart axis. */
  label: string;
  /** The full name in the chart's table, for a screen reader: "Max Verstappen". The code when left out. */
  name?: string;
  start: number;
  end: number;
  /** The line's colour: the team colour, from the data. */
  color: string;
  /** Replaces the start figure: "PL" for a pit-lane start (placed in the last slot). */
  startText?: string;
  /** Replaces the end figure: "DNF L58" for a retirement (placed in its classified slot). */
  endText?: string;
  /**
   * The end is not like for like with the start, as with a retirement. The
   * line is dashed, carries no change figure, and stays grey unless
   * `highlight` says otherwise. The caller still labels the state in `endText`.
   */
  incomplete?: boolean;
  /** Colour this line (`true`) or keep it grey (`false`) whatever the change. */
  highlight?: boolean;
}

export interface SlopeChartProps {
  /** One entry per entity. One without a finite start and end has no line, and is left out. */
  items: readonly SlopeItem[];
  /** The chart's accessible name and its table's caption: "Grid against finish". */
  label: string;
  /** The left column's head: "Grid". */
  startLabel: string;
  /** The right column's head: "Finish". */
  endLabel: string;
  /** `position` (lower is better, P1 on top) or `value` (higher is better). */
  scale?: SlopeScale;
  /** The smallest change drawn in colour; smaller ones stay grey. 0 colours every complete line. */
  emphasis?: number;
  /** The head of the table's name column. */
  nameHeader?: string;
  className?: string;
}

interface Line {
  item: SlopeItem;
  row: SlopeRow;
  delta: number;
  emphasised: boolean;
  startText: string;
  endText: string;
}

const EMPHASISED_WIDTH = 3;
const QUIET_WIDTH = 1.5;
const POINT_RADIUS = 3;
/** Dashed lines fade in over the time solid lines take to draw (`--animate-track-draw`). */
const DASHED_ENTRANCE = { animationDuration: "2.4s" };

/**
 * The change figure's colour. Places gained and lost keep their meanings
 * (`--rc-gain`, red text); a change in value stays neutral, since gain green
 * means positions only. The sign carries the direction either way.
 */
const DELTA_TONE: Record<SlopeScale, Record<SlopeTrend, string>> = {
  position: { gain: "fill-rc-gain", loss: "fill-rc-red-text", even: "fill-rc-ink-3" },
  value: { gain: "fill-rc-ink-2", loss: "fill-rc-ink-2", even: "fill-rc-ink-3" },
};

function toLines(items: readonly SlopeItem[], rows: readonly SlopeRow[], scale: SlopeScale, emphasis: number): Line[] {
  return items.map((item, index) => {
    const delta = slopeDelta(item.start, item.end, scale);
    return {
      item,
      row: rows[index],
      delta,
      emphasised: item.highlight ?? (!item.incomplete && Math.abs(delta) >= emphasis),
      startText: item.startText ?? slopeValueText(item.start, scale),
      endText: item.endText ?? slopeValueText(item.end, scale),
    };
  });
}

function Mark({ line }: { line: Line }) {
  const { item, row, emphasised } = line;
  const stroke = emphasised ? item.color : rc.dim;
  const entrance = item.incomplete
    ? { strokeDasharray: "4 4", className: "motion-safe:animate-overlay-in", style: DASHED_ENTRANCE }
    : { pathLength: 1, strokeDasharray: "1 1", className: "motion-safe:animate-track-draw" };
  return (
    <g data-line={item.id}>
      <path
        d={`M${SLOPE.xStart} ${row.y1} L${SLOPE.xEnd} ${row.y2}`}
        fill="none"
        stroke={stroke}
        strokeWidth={emphasised ? EMPHASISED_WIDTH : QUIET_WIDTH}
        {...entrance}
      />
      <circle cx={SLOPE.xStart} cy={row.y1} r={POINT_RADIUS} fill={stroke} />
      <circle cx={SLOPE.xEnd} cy={row.y2} r={POINT_RADIUS} fill={stroke} />
    </g>
  );
}

function Labels({ line, scale }: { line: Line; scale: SlopeScale }) {
  const { item, row, emphasised, delta } = line;
  const tone = emphasised ? "fill-rc-ink" : "fill-rc-ink-3";
  return (
    <>
      <text
        x={SLOPE.xStart - SLOPE.labelGap}
        y={row.labelY1 + SLOPE.baseline}
        textAnchor="end"
        className={tone}
      >{`${item.label} ${line.startText}`}</text>
      <text x={SLOPE.xEnd + SLOPE.labelGap} y={row.labelY2 + SLOPE.baseline} className={tone}>
        {`${line.endText} ${item.label}`}
        {emphasised && !item.incomplete && (
          <tspan className={DELTA_TONE[scale][trendOf(delta)]}>{` ${deltaText(delta)}`}</tspan>
        )}
      </text>
    </>
  );
}

function DataTable({
  lines,
  scale,
  label,
  heads,
}: {
  lines: Line[];
  scale: SlopeScale;
  label: string;
  heads: string[];
}) {
  return (
    <table className="sr-only">
      <caption>{label}</caption>
      <thead>
        <tr>
          {heads.map((head) => (
            <th key={head} scope="col">
              {head}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {lines.map(({ item, delta, startText, endText }) => (
          <tr key={item.id}>
            <th scope="row">{item.name ?? item.label}</th>
            <td>{startText}</td>
            <td>{endText}</td>
            <td>{item.incomplete ? "not compared" : spokenChange(delta, scale)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Two-point comparison per entity (debrief.html's grid → finish): a line from
 * each entity's start to its end, labelled at both ends with its code and
 * figure, and at the end with its signed change ("+4", "−4"), so a rise reads
 * from the slope and the sign as well as the colour.
 *
 * Lines are team colours from the data. With `emphasis`, only changes at least
 * that big stay coloured and on top; the rest go grey. The drawing is hidden
 * from assistive tech, which gets the same data as a visually hidden table
 * with the change in words. Solid lines draw in once behind `motion-safe`.
 */
export function SlopeChart({
  items,
  label,
  startLabel,
  endLabel,
  scale = "position",
  emphasis = 0,
  nameHeader = "Name",
  className = "",
}: SlopeChartProps) {
  const plotted = items.filter((item) => Number.isFinite(item.start) && Number.isFinite(item.end));
  if (plotted.length === 0) return null;

  const { width, height, rows } = slopeLayout(plotted, scale);
  const lines = toLines(plotted, rows, scale, emphasis);
  const drawOrder = [...lines.filter((line) => !line.emphasised), ...lines.filter((line) => line.emphasised)];

  return (
    <div className={className}>
      <svg viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="block h-auto w-full">
        <g className="fill-rc-ink-3 font-mono text-[11px] font-semibold uppercase" textAnchor="middle">
          <text x={SLOPE.xStart} y={SLOPE.headY}>
            {startLabel}
          </text>
          <text x={SLOPE.xEnd} y={SLOPE.headY}>
            {endLabel}
          </text>
        </g>
        {drawOrder.map((line) => (
          <Mark key={line.item.id} line={line} />
        ))}
        <g className="font-mono text-[11px] font-semibold">
          {lines.map((line) => (
            <Labels key={line.item.id} line={line} scale={scale} />
          ))}
        </g>
      </svg>
      <DataTable lines={lines} scale={scale} label={label} heads={[nameHeader, startLabel, endLabel, "Change"]} />
    </div>
  );
}
