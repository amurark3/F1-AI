"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { DeltaChip } from "@/app/ui/DeltaChip";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { FinalTag, StateTag } from "../grand-prix/StateTag";

import { towerHeading } from "./rewindCopy";
import { stepKind, towerRows } from "./rewindModel";

import type { RaceRewind } from "./rewindTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";

/** The order at the line for the step, every car in the race. */
export function OrderTower({ data, step }: { data: RaceRewind; step: number }) {
  const directory = useSeasonDirectory();
  const heading = towerHeading(data, step, directory);
  const final = stepKind(step, data).kind === "final" ? data.final : null;
  return (
    <figure className={CARD}>
      <PanelHeading
        eyebrow={heading.eyebrow}
        title={heading.title}
        sub={heading.sub}
        aside={final ? <FinalTag final={!final.provisional} /> : undefined}
      />
      <ol>
        {towerRows(data, step).map((row) => (
          <li
            key={row.code}
            className={`grid grid-cols-[22px_3px_38px_minmax(0,1fr)_auto_auto] items-center gap-2 border-b border-rc-line-soft py-[5px] text-xs ${row.out ? "opacity-55" : ""}`}
          >
            <span className="text-right font-mono text-[11px] text-rc-ink-3">{row.place ?? "–"}</span>
            <i
              aria-hidden="true"
              className="block h-3.5 rounded-[1px]"
              style={{ backgroundColor: getTeamColor(row.team) }}
            />
            <b className="font-mono text-xs font-semibold text-rc-ink">{row.code}</b>
            <DriverName name={row.name} code={row.code} className="truncate text-rc-ink-2" />
            {row.tag ? <StateTag>{row.tag}</StateTag> : <span />}
            {row.delta === null ? <span /> : <DeltaChip delta={row.delta} />}
          </li>
        ))}
      </ol>
    </figure>
  );
}
