import { StatTile, StatTiles } from "@/app/ui/StatTile";

import { teamKpis } from "./teamModel";

import type { TeamProfile } from "../../profiles/profilesModel";

/** The season's four counts for the team, each with who earned it. */
export function TeamKpis({ profile }: { profile: TeamProfile }) {
  const { wins, podiums, poles, retirements } = teamKpis(profile);
  return (
    <StatTiles className="mt-5 motion-safe:animate-fade-up">
      <StatTile lead label="Wins" value={wins.value} unit={wins.unit} sub={wins.sub} />
      <StatTile label="Podiums" value={podiums.value} sub={podiums.sub} />
      <StatTile label="Poles" value={poles.value} sub={poles.sub} />
      <StatTile label="Retirements" value={retirements.value} sub={retirements.sub} />
    </StatTiles>
  );
}
