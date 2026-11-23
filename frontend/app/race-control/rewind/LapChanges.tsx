"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { DeltaChip } from "@/app/ui/DeltaChip";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { StateTag } from "../grand-prix/StateTag";

import { changesTitle, surnameFn } from "./rewindCopy";
import { changeDetail, changeLabel, changesAt, driverOf, lapAt, stepKind } from "./rewindModel";

import type { RaceRewind } from "./rewindTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";
const ROW =
  "grid grid-cols-[3px_minmax(0,1fr)_auto_auto] items-center gap-x-2.5 gap-y-1 border-b border-rc-line-soft py-[9px] text-[13px] md:grid-cols-[3px_150px_96px_auto_auto_minmax(0,1fr)]";

/** Each place change on the lap, sorted by why it happened. */
export function LapChanges({ data, step }: { data: RaceRewind; step: number }) {
  const directory = useSeasonDirectory();
  const at = stepKind(step, data);
  const track = lapAt(data, step)?.track ?? null;
  const name = surnameFn(data, directory);
  if (at.kind !== "lap") {
    return (
      <div className={CARD}>
        <PanelHeading eyebrow={`Position changes · ${at.kind === "grid" ? "at the start" : "after the flag"}`} />
        <p className="text-sm text-rc-ink-3">
          {at.kind === "grid"
            ? "The race hasn't started at this step: this is the starting grid."
            : `The flag fell on lap ${data.total_laps}; the card beside this one shows what changed after it.`}
        </p>
      </div>
    );
  }
  return (
    <figure className={CARD}>
      <PanelHeading
        eyebrow={`Position changes · lap ${at.lap}`}
        title={changesTitle(data, at.lap, directory)}
        sub="Each change sorted by why: a stop, a pass, a retirement ahead, or a change under the Safety Car"
      />
      <ul>
        {changesAt(data, step).map((change) => {
          const driver = driverOf(data, change.driver_code);
          return (
            <li key={change.driver_code} className={ROW}>
              <i
                aria-hidden="true"
                className="block h-4 rounded-[1px]"
                style={{ backgroundColor: getTeamColor(driver.team) }}
              />
              <DriverName
                name={driver.driver_name}
                code={driver.driver_code}
                className="truncate font-semibold text-rc-ink"
              />
              <span className="font-mono text-xs text-rc-ink-2">{`P${change.from} → P${change.to}`}</span>
              <DeltaChip delta={change.from - change.to} />
              {/* On a phone the tag and detail take a second row beside the team bar, not inside its 3 px column. */}
              <span className="col-start-2 whitespace-nowrap md:col-start-auto">
                <StateTag>{changeLabel(change, track)}</StateTag>
              </span>
              <span className="col-span-2 text-right text-xs text-rc-ink-3 md:col-auto md:text-left">
                {changeDetail(change, name)}
              </span>
            </li>
          );
        })}
      </ul>
    </figure>
  );
}
