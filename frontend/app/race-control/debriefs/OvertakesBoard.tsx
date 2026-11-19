"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { RankBars } from "@/app/ui/RankBars";

import { overtakesTitle } from "./lapsModel";

import type { DebriefOvertakes } from "./debriefTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";
const SHOWN = 6;

/** The cars that made the most on-track position changes. */
export function OvertakesBoard({ overtakes }: { overtakes: DebriefOvertakes }) {
  const directory = useSeasonDirectory();
  if (!overtakes.available) {
    return (
      <div className={CARD}>
        <PanelHeading eyebrow="Overtakes" />
        <p className="text-sm text-rc-ink-3">OpenF1 has no position changes for this race.</p>
      </div>
    );
  }
  return (
    <div className={CARD}>
      <PanelHeading
        eyebrow="Overtakes"
        title={overtakesTitle(overtakes, directory)}
        sub="On-track position changes made, OpenF1"
      />
      <RankBars
        label="Position changes made"
        items={overtakes.drivers.slice(0, SHOWN).map((driver) => ({
          id: driver.driver_code,
          label: <DriverName name={driver.driver_name} code={driver.driver_code} />,
          value: driver.made,
          color: getTeamColor(driver.team),
        }))}
      />
    </div>
  );
}
