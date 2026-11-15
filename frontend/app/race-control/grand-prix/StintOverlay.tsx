import { redFlagLap, type Neutralisation } from "./strategyModel";

const LANE_INSET = "left-[calc(1rem+6rem+0.75rem)] right-4 sm:right-[calc(1rem+6rem+0.75rem)]";

const BAND_NAME: Record<Neutralisation["kind"], string> = { sc: "SC", vsc: "VSC", red: "Red flag" };

const percent = (laps: number, raceLaps: number): string => `${(laps / raceLaps) * 100}%`;

/**
 * The race's neutralised periods drawn behind every lane: a band for each
 * safety car and virtual safety car, and a line where the red flag stopped the
 * race. The labels sit on two tiers (bands low, red flag high) so a safety car
 * ending in a red flag, as in Mexico City, never has two labels on one spot,
 * however narrow the lane.
 */
export function StintOverlay({
  neutralisations,
  raceLaps,
}: {
  neutralisations: Neutralisation[] | null;
  raceLaps: number;
}) {
  const redLap = redFlagLap(neutralisations);
  const bands = (neutralisations ?? []).filter((period) => period.kind !== "red");
  if (bands.length === 0 && redLap === null) return null;

  return (
    <div className={`pointer-events-none absolute -top-9 bottom-0 ${LANE_INSET}`} aria-hidden="true">
      {bands.map((band) => (
        <span
          key={`${band.kind}-${band.start_lap}`}
          className="absolute bottom-0 top-[18px] border-x border-dashed border-rc-ink-3/40 bg-rc-ink-3/10"
          style={{
            left: percent(band.start_lap - 1, raceLaps),
            width: percent(band.end_lap - band.start_lap + 1, raceLaps),
          }}
          title={`${BAND_NAME[band.kind]} laps ${band.start_lap}-${band.end_lap}`}
        >
          <em className="absolute left-1 top-0 font-mono text-[9px] font-semibold not-italic leading-none tracking-[0.12em] text-rc-ink-3">
            {BAND_NAME[band.kind]}
          </em>
        </span>
      ))}
      {redLap !== null && (
        <span
          className="absolute bottom-0 top-0 border-l border-f1-red"
          style={{ left: percent(redLap, raceLaps) }}
          title={`Red flag after lap ${redLap}`}
        >
          <em className="absolute left-1 top-0 whitespace-nowrap font-mono text-[9px] font-semibold not-italic leading-none tracking-[0.12em] text-rc-red-text">
            RED FLAG · L{redLap}
          </em>
        </span>
      )}
    </div>
  );
}
