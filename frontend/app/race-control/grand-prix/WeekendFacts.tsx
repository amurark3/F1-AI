import { StatTile, StatTiles } from "@/app/ui/StatTile";

import { circuitFacts } from "./weekendTabModel";

import type { CircuitRecord } from "../weekend/weekendTypes";

/** The circuit's four figures, from f1db's record: lap length, laps, race distance and corners. */
export function WeekendFacts({ record }: { record: CircuitRecord | null | undefined }) {
  const facts = circuitFacts(record);
  return (
    <StatTiles>
      <StatTile label="Lap" value={facts.lap} unit="km" />
      <StatTile label="Laps" value={facts.laps} />
      <StatTile label="Distance" value={facts.distance} unit="km" />
      <StatTile label="Corners" value={facts.corners} sub={facts.direction} />
    </StatTiles>
  );
}
