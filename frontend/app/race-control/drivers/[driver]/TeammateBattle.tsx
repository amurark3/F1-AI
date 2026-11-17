import { Legend } from "@/app/ui/Legend";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { h2hRule, h2hTitle, headToHead, otherLabel, surname, type HeadToHead } from "./driverModel";

import type { DriverProfile } from "../../profiles/profilesModel";

const BIG = "font-display font-extrabold leading-none tabular-nums text-rc-ink";
const MONO = "font-mono text-[11px] font-semibold leading-none text-rc-ink-3";

/** The teammate's colour in the chart: the driver's own, at the strength of the bars that are not the story. */
function quiet(color: string): string {
  return `color-mix(in srgb, ${color} 45%, transparent)`;
}

interface CountRowProps {
  mine: number;
  theirs: number;
  mineText: string;
  theirsText: string;
  tag: string;
  size: string;
}

function CountRow({ mine, theirs, mineText, theirsText, tag, size }: CountRowProps) {
  return (
    <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
      <div>
        <b className={`${BIG} ${size}`}>{mine}</b>
        <p className="mt-1 text-xs text-rc-ink-2">{mineText}</p>
      </div>
      <span className={MONO}>{tag}</span>
      <div className="text-right">
        <b className={`${BIG} ${size}`}>{theirs}</b>
        <p className="mt-1 text-xs text-rc-ink-2">{theirsText}</p>
      </div>
    </div>
  );
}

function Battle({ profile, h2h }: { profile: DriverProfile; h2h: HeadToHead }) {
  const color = profile.driver.color;
  const me = surname(profile);
  const mate = otherLabel(profile, h2h.teammate);
  return (
    <>
      <CountRow
        mine={h2h.ahead}
        theirs={h2h.behind}
        mineText={`${me} ahead at the flag`}
        theirsText={`${mate} ahead`}
        tag="RACE"
        size="text-[54px]"
      />
      <div
        role="img"
        aria-label={`Finished ahead: ${me} ${h2h.ahead}, ${mate} ${h2h.behind}`}
        className="mt-2.5 flex h-2.5 overflow-hidden rounded-[5px]"
      >
        <b className="origin-left motion-safe:animate-fill-x" style={{ flexGrow: h2h.ahead, backgroundColor: color }} />
        <b style={{ flexGrow: h2h.behind, backgroundColor: quiet(color) }} />
      </div>
      <CountRow
        mine={h2h.gridAhead}
        theirs={h2h.gridBehind}
        mineText="Started ahead"
        theirsText={`${mate} started ahead`}
        tag="GRID"
        size="text-[40px]"
      />
      <Legend
        className="mt-5"
        items={[
          { label: me, color },
          { label: mate, color: quiet(color) },
        ]}
      />
      <p className="mt-3 text-xs text-rc-ink-3">{[h2hRule(h2h), ...h2h.notCounted].join(" ")}</p>
    </>
  );
}

/** The season against the main teammate: who finished and who started ahead, and the rule that decides it. */
export function TeammateBattle({ profile }: { profile: DriverProfile }) {
  const h2h = headToHead(profile);
  const { year } = profile;
  const eyebrow = h2h ? (
    <>
      Teammate battle · vs{" "}
      <DriverName
        name={h2h.teammate.name}
        lastName={h2h.teammate.last_name}
        code={h2h.teammate.code}
        id={h2h.teammate.id}
        year={year}
      />
    </>
  ) : (
    "Teammate battle"
  );
  return (
    <figure className="min-w-0 rounded-md border border-rc-line bg-(--surface) p-6">
      <PanelHeading eyebrow={eyebrow} title={h2h ? h2hTitle(profile, h2h) : undefined} />
      {h2h ? (
        <Battle profile={profile} h2h={h2h} />
      ) : (
        <p className="text-sm text-rc-ink-3">No race alongside a teammate yet.</p>
      )}
    </figure>
  );
}
