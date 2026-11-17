import { ColumnBars, type ColumnBarItem } from "@/app/ui/ColumnBars";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { formatPoints, type TeamProfile } from "../../profiles/profilesModel";

import { weekendTitle } from "./teamModel";

/** The team's colour at the strength of the bars that are not the story. */
function quiet(color: string): string {
  return `color-mix(in srgb, ${color} 35%, transparent)`;
}

function columns(profile: TeamProfile, best: number): ColumnBarItem[] {
  return profile.rounds
    .filter((round) => round.status === "complete")
    .map((round) => ({
      id: String(round.round),
      axis: `R${round.round}`,
      value: round.points,
      valueText: formatPoints(round.points),
      color: round.points === best ? profile.team.color : quiet(profile.team.color),
      description: `R${round.round} ${round.short_name}: ${formatPoints(round.points)} points`,
    }));
}

/** Constructor points per completed weekend, sprints included, the best weekend in the team colour. */
export function PointsByWeekend({ profile }: { profile: TeamProfile }) {
  const best = Math.max(
    0,
    ...profile.rounds.filter((round) => round.status === "complete").map((round) => round.points),
  );
  return (
    <figure className="rounded-md border border-rc-line bg-(--surface) p-6">
      <PanelHeading
        eyebrow="Including sprints"
        title={weekendTitle(profile)}
        sub="Constructor points per weekend · best weekend highlighted"
      />
      <ColumnBars
        label="Constructor points by round"
        items={columns(profile, best)}
        max={best > 0 ? best : undefined}
        height={200}
      />
    </figure>
  );
}
