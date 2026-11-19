"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { Legend, type LegendItem } from "@/app/ui/Legend";
import { driverLabel } from "@/app/ui/names/names";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { f1, rc } from "@/app/ui/tokens";

import { redFlagLap } from "../grand-prix/strategyModel";

import { stripRuns, stripSub, stripTitle } from "./lapsModel";

import type { DebriefLaps } from "./debriefTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";

/** Who led each lap at the line, one block per lap, with the red flag drawn after its lap. */
export function LapLeaders({ laps }: { laps: DebriefLaps }) {
  const directory = useSeasonDirectory();
  if (!laps.available) {
    return (
      <div className={CARD}>
        <PanelHeading eyebrow="Lap leaders" />
        <p className="text-sm text-rc-ink-3">{laps.reason}</p>
      </div>
    );
  }
  const colorOf = (code: string | null) =>
    code === null ? rc.dim : getTeamColor(laps.drivers.find((driver) => driver.driver_code === code)?.team ?? "");
  const redLap = redFlagLap(laps.neutralisations);
  const leaders = [...new Set(laps.leaders.filter((code): code is string => code !== null))];
  const items: LegendItem[] = leaders.map((code) => ({
    label: driverLabel(
      { name: laps.drivers.find((driver) => driver.driver_code === code)?.driver_name ?? code, code },
      "last",
      directory,
    ),
    color: colorOf(code),
  }));
  if (redLap !== null) items.push({ label: `Red flag after lap ${redLap}`, color: f1.red, mark: "rule" });
  return (
    <div className={CARD}>
      <PanelHeading eyebrow="Lap leaders" title={stripTitle(laps, directory)} sub={stripSub(laps, directory)} />
      <div aria-hidden="true" className="flex h-[26px] gap-[2px]">
        {laps.leaders.map((code, index) => (
          <span key={index} className="contents">
            <span className="flex-1 rounded-[1px]" style={{ backgroundColor: colorOf(code) }} />
            {redLap === index + 1 && <span data-red-flag="" className="w-0.5 bg-f1-red" />}
          </span>
        ))}
      </div>
      <ul className="sr-only">
        {stripRuns(laps).map((run) => (
          <li key={run.range}>{`${run.range}: ${run.name}`}</li>
        ))}
      </ul>
      <Legend items={items} label="Lap leaders" className="mt-3.5" />
    </div>
  );
}
