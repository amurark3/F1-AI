import { StatTile, StatTiles } from "@/app/ui/StatTile";

import { driverKpis } from "./driverModel";

import type { DriverProfile } from "../../profiles/profilesModel";

/** The season's four counts for the driver, each with the rounds behind it. */
export function DriverKpis({ profile }: { profile: DriverProfile }) {
  const { podiums, wins, poles, fastestLaps } = driverKpis(profile);
  return (
    <StatTiles className="mt-5 motion-safe:animate-fade-up">
      <StatTile lead label="Podiums" value={podiums.value} unit={podiums.unit} sub={podiums.sub} />
      <StatTile label="Wins" value={wins.value} sub={wins.sub} />
      <StatTile label="Poles" value={poles.value} sub={poles.sub} />
      <StatTile label="Fastest laps" value={fastestLaps.value} sub={fastestLaps.sub} />
    </StatTiles>
  );
}
