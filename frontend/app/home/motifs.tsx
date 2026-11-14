import { f1, font, rc } from "@/app/ui/tokens";

import type { ToolMotif } from "./content";

/**
 * The homepage's illustrations (docs/design/redesign/home.html). Shapes only:
 * no names, results, counts or team colours, so nothing on them can go stale
 * or wrong between deploys. Each is for the eye only (`aria-hidden`); the card
 * around it carries the words.
 */

/**
 * One right-hander, drawn as the B1 mark's idea at full size: a track of
 * width 56 round a 140-radius corner, and the racing line that enters wide,
 * clips the inside kerb at the apex and runs out wide.
 */
const CORNER = {
  viewBox: "0 0 440 320",
  track: "M60 320 L60 200 A140 140 0 0 1 200 60 L440 60",
  trackWidth: 56,
  line: "M38 320 L38 240 C38 190 76.6 156.6 116.6 116.6 C156.6 76.6 190 38 240 38 L440 38",
  lineWidth: 4,
  apex: { cx: 116.6, cy: 116.6, r: 9 },
  label: { x: 134, y: 146 },
} as const;

export function RacingLine() {
  return (
    <svg viewBox={CORNER.viewBox} aria-hidden="true" focusable="false" className="h-auto w-full">
      <path d={CORNER.track} fill="none" stroke={rc.line} strokeWidth={CORNER.trackWidth} />
      <path
        d={CORNER.line}
        pathLength={1}
        strokeDasharray="1 1"
        fill="none"
        stroke={rc.ink}
        strokeWidth={CORNER.lineWidth}
        strokeLinecap="round"
        className="motion-safe:animate-track-draw"
      />
      <circle data-apex="" cx={CORNER.apex.cx} cy={CORNER.apex.cy} r={CORNER.apex.r} fill={f1.red} />
      <text
        x={CORNER.label.x}
        y={CORNER.label.y}
        fill={rc.ink3}
        fontFamily={font.mono}
        fontSize={13}
        fontWeight={600}
        letterSpacing={2.6}
      >
        APEX
      </text>
    </svg>
  );
}

/** Grand Prix Hub: a season as a row of equal weekends, none singled out. */
const CALENDAR_TICKS = Array.from({ length: 24 }, (_, index) => `tick-${index}`);

function CalendarMotif() {
  return (
    <div className="flex w-full items-end gap-[3px]">
      {CALENDAR_TICKS.map((tick) => (
        <i key={tick} className="h-[22px] flex-1 rounded-[1px] bg-rc-ink-2 opacity-55" />
      ))}
    </div>
  );
}

/** Telemetry Lab: two speed traces through the same corners, one in front. */
const TRACES = {
  lead: "M0 50 C 30 50 40 12 70 12 S 95 14 105 40 S 130 58 150 30 S 185 8 210 10 S 240 46 255 52 S 285 20 300 16",
  chase: "M0 56 C 30 56 40 26 70 24 S 95 22 105 50 S 130 62 150 40 S 185 20 210 20 S 240 54 255 58 S 285 32 300 28",
} as const;

function TracesMotif() {
  return (
    <svg viewBox="0 0 300 64" className="h-16 w-full">
      <path d={TRACES.lead} fill="none" stroke={rc.ink2} strokeWidth={2} />
      <path d={TRACES.chase} fill="none" stroke={rc.dim} strokeWidth={2} strokeDasharray="5 4" />
    </svg>
  );
}

/** Standings: three bars of falling length, unnamed and unnumbered. */
const STANDINGS_BARS = ["w-full", "w-[78%] [animation-delay:80ms]", "w-[62%] [animation-delay:160ms]"];

function StandingsMotif() {
  return (
    <div className="grid w-full gap-[9px]">
      {STANDINGS_BARS.map((bar) => (
        <i
          key={bar}
          className={`block h-1.5 origin-left rounded-[3px] bg-rc-ink-2 opacity-55 motion-safe:animate-fill-x ${bar}`}
        />
      ))}
    </div>
  );
}

/** Teams & Drivers: line-ups as pairs, two seats to a team. */
const LINEUPS = Array.from({ length: 10 }, (_, index) => `team-${index}`);

function LineupsMotif() {
  return (
    <div className="flex h-10 w-full gap-1.5">
      {LINEUPS.map((team) => (
        <span key={team} className="grid flex-1 gap-[3px]">
          <i className="rounded-[2px] bg-rc-ink-2 opacity-55" />
          <i className="rounded-[2px] bg-rc-ink-2 opacity-55" />
        </span>
      ))}
    </div>
  );
}

/** Power Units: elements used per car, a spare left (outline) or one over the allowance (red). */
type Pip = "used" | "spare" | "over";

const PIP_CLASS: Record<Pip, string> = {
  used: "bg-rc-ink-2 opacity-60",
  spare: "border border-rc-line",
  over: "bg-f1-red",
};

const CARS: ReadonlyArray<{ id: string; pips: readonly Pip[] }> = [
  { id: "car-a", pips: ["used", "used", "used", "over"] },
  { id: "car-b", pips: ["used", "used", "spare"] },
  { id: "car-c", pips: ["used", "used", "used", "spare"] },
  { id: "car-d", pips: ["used", "used", "spare"] },
  { id: "car-e", pips: ["used", "spare"] },
  { id: "car-f", pips: ["used", "used", "used", "used", "over"] },
];

function PowerUnitsMotif() {
  return (
    <div className="grid w-full grid-cols-[repeat(auto-fill,minmax(54px,auto))] gap-x-[18px] gap-y-1.5">
      {CARS.map((car) => (
        <div key={car.id} className="flex items-center gap-[3px]">
          {car.pips.map((pip, index) => (
            <i key={`${car.id}-${index}`} className={`h-[22px] w-2.5 rounded-[1px] ${PIP_CLASS[pip]}`} />
          ))}
        </div>
      ))}
    </div>
  );
}

const MOTIFS: Record<ToolMotif, () => React.JSX.Element> = {
  calendar: CalendarMotif,
  traces: TracesMotif,
  standings: StandingsMotif,
  lineups: LineupsMotif,
  powerUnits: PowerUnitsMotif,
};

/** The motif strip at the top of a decision-tool card. */
export function ToolMotifStrip({ motif }: { motif: ToolMotif }) {
  const Motif = MOTIFS[motif];
  return (
    <div aria-hidden="true" className="mb-[18px] flex h-16 items-end">
      <Motif />
    </div>
  );
}
