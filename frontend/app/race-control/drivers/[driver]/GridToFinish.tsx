import { ColumnBars } from "@/app/ui/ColumnBars";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { gridColumns, gridTitle } from "./driverModel";

import type { DriverProfile } from "../../profiles/profilesModel";

/** Places gained or lost from the grid in each race; a retirement shows its code and moves no places. */
export function GridToFinish({ profile }: { profile: DriverProfile }) {
  return (
    <figure className="min-w-0 rounded-md border border-rc-line bg-(--surface) p-6">
      <PanelHeading
        eyebrow="Grid → finish"
        title={gridTitle(profile)}
        sub="Places gained or lost from the starting slot in each race · retirements count no places"
      />
      <ColumnBars label="Places gained or lost by round" items={gridColumns(profile)} height={240} />
    </figure>
  );
}
