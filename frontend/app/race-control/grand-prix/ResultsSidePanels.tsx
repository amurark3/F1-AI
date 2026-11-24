import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { debriefHref } from "@/app/lib/entityLinks";
import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";

import type { ChangedAfterFlag, FastestLap, ResultDriver } from "./resultsModel";

function Who({ driver, year }: { driver: ResultDriver; year: number }) {
  return (
    <span className="inline-flex items-center gap-2 font-semibold text-rc-ink">
      <span className="h-3.5 w-[3px] rounded-full" style={{ background: getTeamColor(driver.team) }} />
      <DriverName variant="codeLast" code={driver.driver_code} name={driver.driver_name} year={year} />
    </span>
  );
}

function ChangedLine({ change, year }: { change: ChangedAfterFlag; year: number }) {
  return (
    <div className="border-b border-rc-line-soft py-2.5">
      <div className="grid grid-cols-[1fr_auto_auto] items-baseline gap-x-3.5">
        <Who driver={change} year={year} />
        <span className="font-mono text-[13px] font-semibold text-rc-ink-2">
          P{change.road_position} → P{change.position}
        </span>
        <span className="text-right font-mono text-xs font-semibold text-rc-red-text">+{change.time_penalty} s</span>
      </div>
      {change.moved_up.length > 0 && (
        <p className="mt-1 text-xs text-rc-ink-3">
          Moved up:{" "}
          {change.moved_up.map((car) => `${car.driver_name} ${car.road_position} → ${car.position}`).join(", ")}
        </p>
      )}
    </div>
  );
}

/** Each post-race time penalty that moved a car: its road place, its classified place, and who it let past. */
export function ChangedAfterFlagPanel({ changes, year }: { changes: ChangedAfterFlag[]; year: number }) {
  if (changes.length === 0) return null;
  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow="Changed after the flag"
        sub="Place on the road → classified place; the penalty is added to the race time"
      />
      {changes.map((change) => (
        <ChangedLine key={change.driver_code} change={change} year={year} />
      ))}
    </Panel>
  );
}

export function FastestLapPanel({ lap, year }: { lap: FastestLap | null; year: number }) {
  if (!lap) return null;
  return (
    <Panel as="section" className="p-5">
      <PanelHeading eyebrow="Fastest lap" />
      <p className="font-display text-[56px] font-extrabold leading-none text-(--f1-sector-best)">{lap.time}</p>
      <p className="mt-2 text-sm text-rc-ink-3">
        <Who driver={lap} year={year} /> · lap {lap.lap}
      </p>
    </Panel>
  );
}

export function DebriefLinkPanel({ round, year }: { round: number; year: number }) {
  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow="The race itself"
        sub="Lap leaders, the red flag, grid to finish and the penalties served in the pits"
      />
      <Link
        href={debriefHref(round, year)}
        className="inline-flex items-center gap-1.5 font-mono text-xs text-rc-blue hover:text-rc-ink"
      >
        Read the debrief
        <ArrowRight className="h-3.5 w-3.5" aria-hidden />
      </Link>
    </Panel>
  );
}
