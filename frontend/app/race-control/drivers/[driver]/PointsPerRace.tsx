import { ColumnBars } from "@/app/ui/ColumnBars";
import { Legend } from "@/app/ui/Legend";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { rc } from "@/app/ui/tokens";

import { pointsColumns, pointsScale, pointsTitle } from "./driverModel";

import type { DriverProfile } from "../../profiles/profilesModel";

/** Grand Prix points of each race: gold for a win, the team's colour for the rest. */
export function PointsPerRace({ profile }: { profile: DriverProfile }) {
  return (
    <figure className="min-w-0 rounded-md border border-rc-line bg-(--surface) p-6">
      <PanelHeading eyebrow="Points per race" title={pointsTitle(profile)} sub="Grand Prix points only · gold = win" />
      <ColumnBars
        label="Grand Prix points by round"
        items={pointsColumns(profile)}
        max={pointsScale(profile)}
        height={160}
      />
      <Legend
        className="mt-3.5"
        items={[
          { label: "Win", color: rc.gold },
          { label: "Points", color: profile.driver.color },
        ]}
      />
    </figure>
  );
}
